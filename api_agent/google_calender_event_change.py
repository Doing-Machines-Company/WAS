# google_calendar_event_change.py

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
    A 'passive' agent that polls Google Calendar for changes to events.

    Features:
      - We do either a full fetch if no sync token or an incremental fetch if we have a sync token.
      - Locally, we maintain a time window [now - X hours, now + Y hours].
      - We keep an event cache of items that are currently in-window (or are still tracked if previously in-window).
      - We keep an _active_tracking_set for events that have ever passed criteria_func while in-window.
        Once in the active set, they remain until the event is:
          (1) pruned for being outside the time window, OR
          (2) actually deleted from the user’s calendar (status="cancelled").
      - We log details about how many events are added/removed from the cache and active set.
      - We print out event_cache size and active_tracking_set size at every poll.
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

        # Where we store event data
        self._event_cache: Dict[str, dict] = {}
        # Events that have met criteria while in-window (remain unless pruned or deleted)
        self._active_tracking_set: set = set()
        # Chronological record of changes
        self._all_changes: List[dict] = []

        # Optional callback for changes to events in _active_tracking_set
        self.on_tracked_event_changed: Optional[Callable[[dict], None]] = None

        # We track if we've done a first fetch yet (for logging)
        self._did_initial_fetch = False

    async def handle_polling(self):
        """
        Periodically called. We do either a full fetch (if no sync token)
        or an incremental fetch. Then we prune out-of-window events,
        and log a summary of how many items are in our cache and active set.
        """
        for cal_id in self.calendar_ids:
            # We track how many items we add/remove in this poll
            self._added_to_cache = 0
            self._removed_from_cache = 0
            self._added_to_active_set = 0
            self._removed_from_active_set = 0

            if not self._last_sync_token:
                # No sync token => full fetch
                if not self._did_initial_fetch:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => doing FIRST-RUN full fetch for {cal_id}.")
                    self._did_initial_fetch = True
                else:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => doing normal full fetch for {cal_id}.")
                await self._handle_full_fetch(cal_id)
            else:
                # We have a sync token => incremental fetch
                logger.info(f"[GCalEventChangeAgent] Doing incremental fetch for {cal_id}.")
                await self._handle_incremental_fetch(cal_id)

            # Prune out-of-window events
            self.prune_out_of_window_events()

            # Log final stats
            logger.info(
                f"[GCalEventChangeAgent] After poll for '{cal_id}':\n"
                f"   event_cache size={len(self._event_cache)}, active_tracking_set size={len(self._active_tracking_set)}\n"
                f"   added_to_cache={self._added_to_cache}, removed_from_cache={self._removed_from_cache}, "
                f"added_to_active_set={self._added_to_active_set}, removed_from_active_set={self._removed_from_active_set}"
            )

    async def _handle_full_fetch(self, cal_id: str):
        """
        Fetch all events (no time filter), store them in the cache if they're in-window,
        record a syncToken if provided. Then log how many were in vs out of the timeframe.
        """
        try:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                orderBy="updated"
            ).execute()
        except HttpError as e:
            logger.error(f"[GCalEventChangeAgent] HttpError during full fetch: {e}")
            return

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Full fetch returned {len(items)} events for {cal_id}.")

        in_timeframe_count = 0
        out_of_timeframe_count = 0

        for ev in items:
            is_in_timeframe = self._process_incremental_change(ev)
            if is_in_timeframe:
                in_timeframe_count += 1
            else:
                out_of_timeframe_count += 1

        # store sync token if provided
        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

        logger.info(
            f"[GCalEventChangeAgent] => {len(items)} items processed. "
            f"{in_timeframe_count} in timeframe, {out_of_timeframe_count} out of timeframe."
        )

    async def _handle_incremental_fetch(self, cal_id: str):
        """
        Use stored syncToken to do an incremental fetch. Then feed them
        to _process_incremental_change.
        """
        try:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                syncToken=self._last_sync_token
            ).execute()
        except HttpError as e:
            if e.resp and e.resp.status == 410:
                logger.warning("[GCalEventChangeAgent] Sync token expired => next time we'll do a full fetch.")
                self._last_sync_token = None
                return
            else:
                logger.error(f"[GCalEventChangeAgent] HttpError during incremental fetch: {e}")
                return

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Incremental fetch returned {len(items)} changed events for {cal_id}.")

        in_timeframe_count = 0
        out_of_timeframe_count = 0

        for ev in items:
            is_in_timeframe = self._process_incremental_change(ev)
            if is_in_timeframe:
                in_timeframe_count += 1
            else:
                out_of_timeframe_count += 1

        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

        logger.info(
            f"[GCalEventChangeAgent] => {len(items)} changed items processed. "
            f"{in_timeframe_count} in timeframe, {out_of_timeframe_count} out of timeframe."
        )

    def _process_incremental_change(self, ev: dict) -> bool:
        """
        Compare event vs our cache => figure out 'created','updated','deleted','no-change'.
        If it's in window, keep/update in cache; if out of window, remove from cache.
        If it's in active set, we do a callback on real changes (not 'no-change').

        Return True if the final result is that the event is in the time window, else False.
        """
        # Default to out_of_timeframe
        in_timeframe = False

        ev_id = ev.get("id", "")
        change_description = self._describe_change(ev)
        self._all_changes.append(change_description)

        old_in_cache = (ev_id in self._event_cache)
        old_in_active = (ev_id in self._active_tracking_set)

        change_type = change_description["change_type"]
        if change_type == "deleted":
            # The user has deleted/cancelled the event.
            # According to your new rule:
            #   => Remove it from the active set, because it's truly removed from the calendar
            if old_in_active:
                self._active_tracking_set.remove(ev_id)
                self._removed_from_active_set += 1
            # Keep it in cache if still in timeframe?
            # If you want to keep 'cancelled' events in the window until they pass:
            if self._within_time_window(ev):
                # If it was never in the cache, we add it
                if not old_in_cache:
                    self._event_cache[ev_id] = ev
                    self._added_to_cache += 1
                else:
                    # Just update the cache
                    self._event_cache[ev_id] = ev
                in_timeframe = True
            else:
                # It's out of the window => remove from cache if present
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1
        else:
            # Not deleted => check if in time window
            if self._within_time_window(ev):
                in_timeframe = True
                if not old_in_cache:
                    self._event_cache[ev_id] = ev
                    self._added_to_cache += 1
                else:
                    # it was in the cache, just update it
                    self._event_cache[ev_id] = ev

                # If it EVER meets criteria while in-window, we add to the active set.
                # We do NOT remove it from active set if it fails the criteria now
                # (the new #2 requirement).
                if self.criteria_func(ev) and not old_in_active:
                    self._active_tracking_set.add(ev_id)
                    self._added_to_active_set += 1
            else:
                # out of timeframe => remove from cache if it was there
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1
                # If it was in the active set, it remains there only if we wanted to keep out-of-window items.
                # But typically, once out of timeframe, we prune it from active as well.
                # So let's remove it from active set:
                if old_in_active:
                    self._active_tracking_set.remove(ev_id)
                    self._removed_from_active_set += 1

        # If it's in the active set now and the change_type != no-change => callback
        new_in_active = (ev_id in self._active_tracking_set)
        if new_in_active and change_type != "no-change" and self.on_tracked_event_changed:
            self.on_tracked_event_changed(change_description)

        return in_timeframe

    def _describe_change(self, ev: dict) -> dict:
        """
        'deleted' if event's status=cancelled,
        'created' if not in cache,
        'updated' if in cache and something changed,
        'no-change' if in cache but no fields changed.
        """
        ev_id = ev.get("id", "")
        status = ev.get("status", "")
        old_event = self._event_cache.get(ev_id, {})

        if status == "cancelled":
            change_type = "deleted"
            diffs = self._compute_diff(old_event, ev)
        else:
            if not old_event:
                change_type = "created"
                diffs = self._compute_diff({}, ev)
            else:
                diffs = self._compute_diff(old_event, ev)
                change_type = "updated" if diffs else "no-change"

        return {
            "id": ev_id,
            "change_type": change_type,
            "status": status,
            "diffs": diffs,
        }

    def _compute_diff(self, old_event: dict, new_event: dict) -> dict:
        """
        Shallow diff:
            { fieldName: {"old": val, "new": val}, ... }
        """
        changes = {}
        all_keys = set(old_event.keys()).union(new_event.keys())
        for k in all_keys:
            old_val = old_event.get(k)
            new_val = new_event.get(k)
            if old_val != new_val:
                changes[k] = {"old": old_val, "new": new_val}
        return changes

    def _within_time_window(self, event: dict) -> bool:
        """
        True if [ev_start, ev_end] intersects [window_start, window_end].
        """
        win_start, win_end = self._compute_time_window()
        ev_start = self._parse_event_start(event)
        ev_end = self._parse_event_end(event)
        if not ev_start or not ev_end:
            return False
        return not (ev_end < win_start or ev_start > win_end)

    def _compute_time_window(self):
        """
        Return (start, end) for local time window in naive UTC datetimes.
        """
        now = datetime.utcnow()
        start = now - timedelta(hours=self.time_window_past_hours)
        end = now + timedelta(hours=self.time_window_future_hours)
        return start, end

    def _parse_event_start(self, event: dict) -> Optional[datetime]:
        """
        Parse start from 'start.dateTime' or 'start.date'.
        """
        start_info = event.get("start", {})
        dt_str = start_info.get("dateTime") or start_info.get("date")
        if not dt_str:
            return None
        try:
            dt = dateutil.parser.isoparse(dt_str)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    def _parse_event_end(self, event: dict) -> Optional[datetime]:
        """
        Parse end from 'end.dateTime' or 'end.date'.
        """
        end_info = event.get("end", {})
        dt_str = end_info.get("dateTime") or end_info.get("date")
        if not dt_str:
            return None
        try:
            dt = dateutil.parser.isoparse(dt_str)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return None

    def prune_out_of_window_events(self):
        """
        Remove from cache any events that no longer belong in our time window.
        Also remove them from active set if they get pruned.
        """
        to_remove = []
        for ev_id, ev in self._event_cache.items():
            if not self._within_time_window(ev):
                to_remove.append(ev_id)

        for ev_id in to_remove:
            del self._event_cache[ev_id]
            self._removed_from_cache += 1
            if ev_id in self._active_tracking_set:
                self._active_tracking_set.remove(ev_id)
                self._removed_from_active_set += 1

    async def new_criteria_reset(self, new_criteria_func: Callable[[dict], bool]):
        """
        Poll immediately (full or incremental), then recalc _active_tracking_set
        with the new criteria, but don't remove items from it if they fail the new criteria
        (since once tracked, we keep them unless deleted or out-of-window).
        Then prune out-of-window again, and log final sizes.
        """
        self.criteria_func = new_criteria_func

        # Zero out the counters so we can log them after
        self._added_to_cache = 0
        self._removed_from_cache = 0
        self._added_to_active_set = 0
        self._removed_from_active_set = 0

        for cal_id in self.calendar_ids:
            if not self._last_sync_token:
                logger.info(f"[GCalEventChangeAgent] new_criteria_reset => FULL fetch for {cal_id}.")
                await self._handle_full_fetch(cal_id)
            else:
                logger.info(f"[GCalEventChangeAgent] new_criteria_reset => incremental fetch for {cal_id}.")
                await self._handle_incremental_fetch(cal_id)

        # At this point we do NOT remove anything from active set if it fails the new criteria,
        # because once tracked, we keep it until pruned or deleted.

        # Then prune out-of-window
        self.prune_out_of_window_events()

        # final logging
        for cal_id in self.calendar_ids:
            logger.info(
                f"[GCalEventChangeAgent] After new_criteria_reset for '{cal_id}':\n"
                f"   event_cache size={len(self._event_cache)}, active_tracking_set size={len(self._active_tracking_set)}\n"
                f"   added_to_cache={self._added_to_cache}, removed_from_cache={self._removed_from_cache}, "
                f"added_to_active_set={self._added_to_active_set}, removed_from_active_set={self._removed_from_active_set}"
            )

    def get_all_changes(self) -> List[dict]:
        """
        Chronological list of all changes observed so far.
        """
        return self._all_changes

    def get_active_tracked_events(self) -> List[dict]:
        """
        Return the list of actual event objects for all IDs in the active set
        (that remain in the cache).
        """
        return [
            self._event_cache[eid]
            for eid in self._active_tracking_set
            if eid in self._event_cache
        ]

    def get_in_window_events(self) -> List[dict]:
        """
        Return all events currently in our local in-window cache.
        """
        return list(self._event_cache.values())
