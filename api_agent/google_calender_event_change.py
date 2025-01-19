import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any
from datetime import datetime, timedelta, timezone

import dateutil.parser
from googleapiclient.errors import HttpError

from passive_api_agent import PassiveAPIAgent
from api_functions import GoogleCalendarAPIHandler

logger = logging.getLogger(__name__)


class GCalEventChangeAgent(PassiveAPIAgent):
    """
    A 'passive' agent that polls Google Calendar for changes to events,
    restricted to a rolling time window [now - time_window_past_hours, now + time_window_future_hours].

    Key points:
      - If we have no sync token, we do a window fetch (we call the first one "first-run" once).
      - If we get a sync token from the server, subsequent polls do incremental sync.
      - If the server never gives a sync token, we continue doing window fetches each time
        (but we only call it "first-run" once).
      - For every fetched/changed event, we detect "created"/"updated"/"deleted" by diffing
        against our in-memory cache, triggering callbacks for events in the _active_tracking_set.
      - _active_tracking_set: set of event_ids that have ever passed criteria_func while in-window.
      - prune_out_of_window_events() removes old events that left the time window.
      - new_criteria_reset() can do an immediate poll and re-check all cached events with a new criteria.
    """

    def __init__(
            self,
            check_interval_seconds: int,
            calendar_handler: Optional[GoogleCalendarAPIHandler],
            criteria_func: Callable[[dict], bool],
            time_window_past_hours: int,
            time_window_future_hours: int,
            calendar_ids: Optional[List[str]] = None,
            last_sync_token: Optional[str] = None
    ):
        super().__init__(check_interval_seconds)
        self.calendar_handler = calendar_handler or GoogleCalendarAPIHandler()
        self.criteria_func = criteria_func
        self.calendar_ids = calendar_ids or ["primary"]
        self._last_sync_token = last_sync_token

        self.time_window_past_hours = time_window_past_hours
        self.time_window_future_hours = time_window_future_hours

        # Caches & tracking sets
        self._event_cache: Dict[str, dict] = {}  # event_id -> latest event data
        self._active_tracking_set: set = set()  # event_ids that have passed criteria while in-window
        self._all_changes: List[dict] = []  # chronological record of changes

        # We track if we've done the initial fetch once. If we have no syncToken
        # and haven't done initial fetch yet => "first-run".
        # If no syncToken but we've already done a fetch => just do a normal window fetch.
        self._did_initial_fetch = False

        # Optional callback to notify about changes to tracked events
        self.on_tracked_event_changed: Optional[Callable[[dict], None]] = None

    async def handle_polling(self):
        """
        The periodic polling method:
          - If we have a sync token, do incremental sync.
          - Otherwise, do a window fetch. The very first time is "first-run fetch",
            subsequent times are "window fetch" if we still have no sync token.
          - Then prune events that are out of the time window.
        """
        for cal_id in self.calendar_ids:
            if self._last_sync_token:
                # We have a sync token => do incremental fetch
                await self._handle_incremental_run(cal_id)
            else:
                # No sync token => do a window fetch
                if not self._did_initial_fetch:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => doing FIRST-RUN window fetch for {cal_id}.")
                    self._did_initial_fetch = True
                else:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => doing normal window fetch for {cal_id}.")
                await self._handle_window_fetch(cal_id)

        # After polling, remove events that left the window
        self.prune_out_of_window_events()

    async def _handle_window_fetch(self, cal_id: str):
        """
        Fetch events in [now - Xh, now + Yh].
        For each fetched event, run _process_incremental_change() so that
        "created"/"updated" diffs are computed and callbacks can be triggered.
        If the server returns a nextSyncToken, we store it for future incremental sync.
        """
        win_start, win_end = self._compute_time_window()
        time_min_str = self._to_rfc3339_utc(win_start)
        time_max_str = self._to_rfc3339_utc(win_end)

        try:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                orderBy="startTime",
                timeMin=time_min_str,
                timeMax=time_max_str
            ).execute()
        except HttpError as e:
            logger.error(f"[GCalEventChangeAgent] HttpError during window fetch: {e}")
            return

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Window fetch returned {len(items)} events for {cal_id}.")

        # For each item, do incremental-style processing => triggers "created"/"updated" diffs if new or changed
        for ev in items:
            self._process_incremental_change(ev)

        # Possibly store syncToken
        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

    async def _handle_incremental_run(self, cal_id: str):
        """
        Use the stored syncToken to do an incremental fetch.
        We'll receive changes for events (possibly inside or outside the window).
        We only keep them if the event is in-window or in _active_tracking_set.
        """
        logger.info(f"[GCalEventChangeAgent] Using syncToken => incremental fetch for {cal_id}.")
        try:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                syncToken=self._last_sync_token
            ).execute()
        except HttpError as e:
            if e.resp and e.resp.status == 410:
                # Sync token invalid => reset
                logger.warning("[GCalEventChangeAgent] Sync token expired => will do full window fetch next time.")
                self._last_sync_token = None
                return
            else:
                logger.error(f"[GCalEventChangeAgent] HttpError during incremental fetch: {e}")
                return

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Incremental fetch returned {len(items)} changed events for {cal_id}.")

        for ev in items:
            self._process_incremental_change(ev)

        # update sync token if provided
        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

    def _process_incremental_change(self, ev: dict):
        """
        Determine what changed vs our cache, update the cache,
        and if the event is in _active_tracking_set, invoke callback.
        """
        ev_id = ev.get("id", "")
        change_description = self._describe_change(ev)
        self._all_changes.append(change_description)

        # Update the cache according to "deleted" or normal
        if change_description["change_type"] == "deleted":
            # "cancelled" => keep it in cache if it's still in the time window
            # (the event data is now status=cancelled).
            if ev_id in self._event_cache:
                self._event_cache[ev_id] = ev
        else:
            # Not deleted => check if it's in-window
            if self._within_time_window(ev):
                self._event_cache[ev_id] = ev
                # If it passes criteria, ensure it's tracked
                if self.criteria_func(ev):
                    self._active_tracking_set.add(ev_id)
            else:
                # It's outside the window => remove from cache & tracking set
                if ev_id in self._event_cache:
                    del self._event_cache[ev_id]
                if ev_id in self._active_tracking_set:
                    self._active_tracking_set.remove(ev_id)

        # If the event is in _active_tracking_set, do callback
        if ev_id in self._active_tracking_set and self.on_tracked_event_changed:
            # Only fire callback if change_type != "no-change"
            # but you might want to call it even on no-change if you want a repeated notification
            if change_description["change_type"] != "no-change":
                self.on_tracked_event_changed(change_description)

    def _describe_change(self, ev: dict) -> dict:
        """
        Compare ev to our cache: is it 'created', 'updated', or 'deleted'?
        Also build a shallow diff of changed fields.
        """
        ev_id = ev.get("id", "")
        status = ev.get("status", "")  # "confirmed", "cancelled", etc.
        old_event = self._event_cache.get(ev_id, {})

        if status == "cancelled":
            change_type = "deleted"
            diffs = self._compute_diff(old_event, ev)
        else:
            if not old_event:
                # brand new to us
                change_type = "created"
                diffs = self._compute_diff({}, ev)
            else:
                diffs = self._compute_diff(old_event, ev)
                change_type = "updated" if diffs else "no-change"

        return {
            "id": ev_id,
            "change_type": change_type,
            "status": status,
            "diffs": diffs
        }

    def _compute_diff(self, old_event: dict, new_event: dict) -> dict:
        """
        Simple shallow-diff between old_event and new_event fields.
        Returns { fieldName: {"old": val, "new": val}, ... } for changed fields.
        """
        changes = {}
        all_keys = set(old_event.keys()).union(new_event.keys())
        for k in all_keys:
            old_val = old_event.get(k)
            new_val = new_event.get(k)
            if old_val != new_val:
                changes[k] = {"old": old_val, "new": new_val}
        return changes

    def _compute_time_window(self):
        """
        Return (start_dt, end_dt) for the current time window (naive UTC datetimes).
        """
        now = datetime.utcnow()
        start = now - timedelta(hours=self.time_window_past_hours)
        end = now + timedelta(hours=self.time_window_future_hours)
        return start, end

    def _to_rfc3339_utc(self, dt: datetime) -> str:
        """
        Convert a naive UTC datetime to an RFC3339 string with 'Z' suffix.
        """
        dt_utc = dt.replace(tzinfo=timezone.utc)
        iso_str = dt_utc.isoformat()
        if iso_str.endswith("+00:00"):
            iso_str = iso_str[:-6] + "Z"
        return iso_str

    def _within_time_window(self, event: dict) -> bool:
        """
        Decide if an event is in the rolling time window:
          [now - Xh, now + Yh].
        We'll say it's in-window if event's end >= window start,
        and event's start <= window end.
        """
        win_start, win_end = self._compute_time_window()
        ev_start = self._parse_event_start(event)
        ev_end = self._parse_event_end(event)

        if not ev_start or not ev_end:
            return False

        # Overlap check
        if ev_end < win_start:
            return False
        if ev_start > win_end:
            return False
        return True

    def _parse_event_start(self, event: dict) -> Optional[datetime]:
        """
        Parse event's start time from 'start.dateTime' or 'start.date'.
        Return a naive UTC datetime or None on failure.
        """
        start_info = event.get("start", {})
        dt_str = start_info.get("dateTime") or start_info.get("date")
        if not dt_str:
            return None
        try:
            dt = dateutil.parser.isoparse(dt_str)
            if not dt.tzinfo:
                return dt
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    def _parse_event_end(self, event: dict) -> Optional[datetime]:
        """
        Parse event's end time from 'end.dateTime' or 'end.date'.
        Return a naive UTC datetime or None on failure.
        """
        end_info = event.get("end", {})
        dt_str = end_info.get("dateTime") or end_info.get("date")
        if not dt_str:
            return None
        try:
            dt = dateutil.parser.isoparse(dt_str)
            if not dt.tzinfo:
                return dt
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    def prune_out_of_window_events(self):
        """
        Remove events from _event_cache and _active_tracking_set that
        no longer fall within the current time window.
        """
        to_remove = []
        for ev_id, ev in self._event_cache.items():
            if not self._within_time_window(ev):
                to_remove.append(ev_id)

        for ev_id in to_remove:
            del self._event_cache[ev_id]
            if ev_id in self._active_tracking_set:
                self._active_tracking_set.remove(ev_id)

    async def new_criteria_reset(self, new_criteria_func: Callable[[dict], bool]):
        """
        Immediately poll (incremental if we have a syncToken, or window fetch if not),
        then rebuild _active_tracking_set from the new criteria_func.
        The newly fetched items also get processed => triggers "created"/"updated"/"deleted"
        for changes.
        """
        self.criteria_func = new_criteria_func

        # Perform an immediate poll
        for cal_id in self.calendar_ids:
            if self._last_sync_token:
                await self._handle_incremental_run(cal_id)
            else:
                # If we already did initial fetch before, skip repeating that message
                if not self._did_initial_fetch:
                    logger.info(
                        f"[GCalEventChangeAgent] new_criteria_reset => doing FIRST-RUN window fetch for {cal_id}.")
                    self._did_initial_fetch = True
                else:
                    logger.info(f"[GCalEventChangeAgent] new_criteria_reset => doing normal window fetch for {cal_id}.")
                await self._handle_window_fetch(cal_id)

        # Recompute _active_tracking_set from current cache
        new_set = set()
        for ev_id, ev in self._event_cache.items():
            if self.criteria_func(ev):
                new_set.add(ev_id)
        self._active_tracking_set = new_set

        # Prune out-of-window events
        self.prune_out_of_window_events()

    def get_all_changes(self) -> List[dict]:
        """
        Return the chronological list of all changes observed so far.
        """
        return self._all_changes

    def get_active_tracked_events(self) -> List[dict]:
        """
        Return the actual list of event objects for all IDs in _active_tracking_set.
        """
        return [
            self._event_cache[ev_id]
            for ev_id in self._active_tracking_set
            if ev_id in self._event_cache
        ]

    def get_in_window_events(self) -> List[dict]:
        """
        Return all events currently in our in-window cache (regardless of whether they match criteria).
        """
        return list(self._event_cache.values())
