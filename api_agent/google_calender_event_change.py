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

    Updates per your requests:
      1) Each event in _event_cache now maintains a 'current' snapshot
         plus a 'versions' list to track all historical changes.
      2) If an event in the active set is deleted (status=cancelled),
         a callback is fired.
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

        # Where we store event data (including historical versions).
        #
        # Structure:
        #   _event_cache[event_id] = {
        #       "current": <dict> the current snapshot of the event,
        #       "versions": [    # list of snapshots (dict) representing historical changes
        #           {
        #               "timestamp": <datetime of the poll when change was seen>,
        #               "event": <the event data at that point in time>
        #           },
        #           ...
        #       ]
        #   }
        #
        self._event_cache: Dict[str, dict] = {}

        # Events that have met criteria while in-window (remain unless pruned or deleted)
        self._active_tracking_set: set = set()

        # Chronological record of changes (lightweight "change_type + diffs" log)
        self._all_changes: List[dict] = []

        # Optional callback for changes to events *in* _active_tracking_set
        # or if a tracked event is deleted.
        self.on_tracked_change: Optional[Callable[[dict], None]] = None

        # We track if we've done a first fetch yet (for logging)
        self._did_initial_fetch = False

    async def handle_polling(self):
        """
        Periodically called. We do either a full fetch (if no sync token)
        or an incremental fetch. Then we prune out-of-window events,
        and log a summary of how many items are in our cache and active set.
        """
        for cal_id in self.calendar_ids:
            # Keep counters for logging
            self._added_to_cache = 0
            self._removed_from_cache = 0
            self._added_to_active_set = 0
            self._removed_from_active_set = 0

            if not self._last_sync_token:
                # No sync token => full fetch
                if not self._did_initial_fetch:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => FIRST-RUN full fetch for {cal_id}.")
                    self._did_initial_fetch = True
                else:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => normal full fetch for {cal_id}.")
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
        If in the time window, keep/update in the cache. If out of window, remove from cache.
        If it's in the active set, we do a callback on real changes. Also, if an active item
        is deleted, we trigger the callback.

        Returns True if the final result is that the event is in the time window, else False.
        """
        ev_id = ev.get("id", "")
        # figure out the type of change
        change_description = self._describe_change(ev)
        change_type = change_description["change_type"]
        self._all_changes.append(change_description)

        # were we tracking this event before?
        old_in_cache = (ev_id in self._event_cache)
        old_in_active = (ev_id in self._active_tracking_set)

        if change_type == "deleted":
            # The user has deleted/cancelled the event from the calendar
            #
            # 1) If it was in the active set, trigger callback, then remove from active
            if old_in_active and self.on_tracked_change:
                self.on_tracked_change(change_description)
            if old_in_active:
                self._active_tracking_set.remove(ev_id)
                self._removed_from_active_set += 1

            # 2) Possibly update or remove it in the cache:
            #    If still within window, we keep a final "deleted" version
            #    so that the historical record is there if needed.
            in_timeframe = self._within_time_window(ev)
            if in_timeframe:
                # If it wasn't in the cache, create a record
                rec = self._event_cache.get(ev_id)
                if not rec:
                    rec = {"current": None, "versions": []}
                    self._event_cache[ev_id] = rec
                    self._added_to_cache += 1

                # add this new version to the history
                if change_type != "no-change":
                    rec["versions"].append({
                        "timestamp": datetime.utcnow(),
                        "event": ev.copy()
                    })
                # mark current
                rec["current"] = ev

            else:
                # if it was in the cache, remove it entirely
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1

        else:
            # It's not deleted => normal event
            in_timeframe = self._within_time_window(ev)
            if in_timeframe:
                # update or create in cache
                rec = self._event_cache.get(ev_id)
                if not rec:
                    rec = {"current": None, "versions": []}
                    self._event_cache[ev_id] = rec
                    self._added_to_cache += 1

                # If there's an actual change (created or updated), store a snapshot in versions
                if change_type != "no-change":
                    rec["versions"].append({
                        "timestamp": datetime.utcnow(),
                        "event": ev.copy()
                    })

                # Update current event
                rec["current"] = ev

                # If it meets criteria and wasn't previously in active => add
                if self.criteria_func(ev) and not old_in_active:
                    self._active_tracking_set.add(ev_id)
                    self._added_to_active_set += 1

            else:
                # Out of timeframe => prune from cache if present
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1

                # Also remove it from active set
                if old_in_active:
                    self._active_tracking_set.remove(ev_id)
                    self._removed_from_active_set += 1

            # If new_in_active and there's a real change => callback
            new_in_active = (ev_id in self._active_tracking_set)
            if new_in_active and change_type != "no-change" and self.on_tracked_change:
                self.on_tracked_change(change_description)

        return self._within_time_window(ev)

    def _describe_change(self, ev: dict) -> dict:
        """
        'deleted' if event's status=cancelled,
        'created' if not in cache,
        'updated' if in cache and something changed,
        'no-change' if in cache but no fields changed.
        """
        ev_id = ev.get("id", "")
        status = ev.get("status", "")
        rec = self._event_cache.get(ev_id)
        old_event = rec["current"] if rec else {}

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
        for ev_id, rec in self._event_cache.items():
            current_event = rec["current"]
            if not current_event:
                # If there's no actual event data, remove
                to_remove.append(ev_id)
                continue
            if not self._within_time_window(current_event):
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
        (once tracked, we keep them unless deleted or out-of-window).
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

        # Don't forcibly remove anything from the active set if they fail the new criteria now.
        # We only remove them if they go out of window or are deleted.

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
        Chronological list of all changes observed so far (lightweight).
        """
        return self._all_changes

    def get_active_tracked_events(self) -> List[dict]:
        """
        Return the list of *current* event objects for all IDs in the active set
        that remain in the cache.
        """
        results = []
        for ev_id in self._active_tracking_set:
            if ev_id in self._event_cache:
                rec = self._event_cache[ev_id]
                if rec["current"]:
                    results.append(rec["current"])
        return results

    def get_in_window_events(self) -> List[dict]:
        """
        Return all *current* events in our local in-window cache.
        """
        return [
            rec["current"]
            for rec in self._event_cache.values()
            if rec["current"] is not None
        ]
