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
         a callback is fired (and we remove it from active set).
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

        # event_id => {
        #   "current": <dict>,
        #   "versions": [ { "timestamp": <datetime>, "event": <dict> }, ... ]
        # }
        self._event_cache: Dict[str, dict] = {}

        # event_ids that have met criteria => remain unless pruned or deleted
        self._active_tracking_set: set = set()

        # Chronological record of changes
        self._all_changes: List[dict] = []

        # Now on_tracked_change always takes a dictionary keyed by event_id
        # each containing {"data": ..., "just_changed": bool}
        self.on_tracked_change: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        # We track if we've done a first fetch yet
        self._did_initial_fetch = False

    async def handle_polling(self):
        """
        Periodically called.
        - For each calendar ID, do full or incremental fetch.
        - Then prune out-of-window events.
        - Collect which event IDs changed this round.
        - Finally, invoke the unified callback with the entire active set.
        """
        changed_ids = set()

        for cal_id in self.calendar_ids:
            # Keep counters for logging
            self._added_to_cache = 0
            self._removed_from_cache = 0
            self._added_to_active_set = 0
            self._removed_from_active_set = 0

            # Do a full or incremental fetch
            if not self._last_sync_token:
                if not self._did_initial_fetch:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => FIRST-RUN full fetch for {cal_id}.")
                    self._did_initial_fetch = True
                else:
                    logger.info(f"[GCalEventChangeAgent] No syncToken => normal full fetch for {cal_id}.")
                newly_changed = await self._handle_full_fetch(cal_id)
            else:
                logger.info(f"[GCalEventChangeAgent] Doing incremental fetch for {cal_id}.")
                newly_changed = await self._handle_incremental_fetch(cal_id)

            changed_ids.update(newly_changed)

            # Prune out-of-window
            self.prune_out_of_window_events()

            # Log
            logger.info(
                f"[GCalEventChangeAgent] After poll for '{cal_id}':\n"
                f"   event_cache size={len(self._event_cache)}, active_tracking_set size={len(self._active_tracking_set)}\n"
                f"   added_to_cache={self._added_to_cache}, removed_from_cache={self._removed_from_cache}, "
                f"added_to_active_set={self._added_to_active_set}, removed_from_active_set={self._removed_from_active_set}"
            )

        # Final callback with entire active set
        if self.on_tracked_change:
            payload = {}
            for ev_id in self._active_tracking_set:
                rec = self._event_cache[ev_id]
                payload[ev_id] = {
                    "data": rec["current"],
                    "just_changed": (ev_id in changed_ids)
                }
            self.on_tracked_change(payload)

    async def _handle_full_fetch(self, cal_id: str) -> set:
        """
        Fetch all events, store them if in-window, record syncToken if present.
        Return set of event_ids that changed in this operation.
        """
        changed_ids = set()
        try:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                orderBy="updated"
            ).execute()
        except HttpError as e:
            logger.error(f"[GCalEventChangeAgent] HttpError during full fetch: {e}")
            return changed_ids

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Full fetch returned {len(items)} events for {cal_id}.")

        in_timeframe_count = 0
        out_of_timeframe_count = 0

        for ev in items:
            is_in_timeframe = self._process_incremental_change(ev, changed_ids)
            if is_in_timeframe:
                in_timeframe_count += 1
            else:
                out_of_timeframe_count += 1

        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

        logger.info(
            f"[GCalEventChangeAgent] => {len(items)} items processed. "
            f"{in_timeframe_count} in timeframe, {out_of_timeframe_count} out of timeframe."
        )
        return changed_ids

    async def _handle_incremental_fetch(self, cal_id: str) -> set:
        """
        Use stored syncToken to do an incremental fetch; return set of changed event_ids.
        """
        changed_ids = set()
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
                return changed_ids
            else:
                logger.error(f"[GCalEventChangeAgent] HttpError during incremental fetch: {e}")
                return changed_ids

        items = resp.get("items", [])
        logger.info(f"[GCalEventChangeAgent] Incremental fetch returned {len(items)} changed events for {cal_id}.")

        in_timeframe_count = 0
        out_of_timeframe_count = 0

        for ev in items:
            is_in_timeframe = self._process_incremental_change(ev, changed_ids)
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
        return changed_ids

    def _process_incremental_change(self, ev: dict, changed_ids: set) -> bool:
        """
        Compare event vs our cache => figure out 'created','updated','deleted','no-change'.
        Update the cache if in-window or remove if out-of-window.
        If in active set => mark changed if real update or deletion.
        If newly meets criteria => add & mark changed.
        Return True if event is in-window, else False.
        """
        ev_id = ev.get("id", "")
        # figure out the type of change
        change_description = self._describe_change(ev)
        change_type = change_description["change_type"]
        self._all_changes.append(change_description)

        old_in_cache = (ev_id in self._event_cache)
        old_in_active = (ev_id in self._active_tracking_set)

        if change_type == "deleted":
            # if in active => remove & mark changed
            if old_in_active:
                changed_ids.add(ev_id)
                self._active_tracking_set.remove(ev_id)
                self._removed_from_active_set += 1

            # keep final "deleted" version if in-window, else remove
            in_timeframe = self._within_time_window(ev)
            if in_timeframe:
                rec = self._event_cache.get(ev_id)
                if not rec:
                    rec = {"current": None, "versions": []}
                    self._event_cache[ev_id] = rec
                    self._added_to_cache += 1

                # record historical version
                if change_type != "no-change":
                    rec["versions"].append({
                        "timestamp": datetime.utcnow(),
                        "event": ev.copy()
                    })
                rec["current"] = ev
            else:
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1
            return in_timeframe

        else:
            # not deleted => normal event
            in_timeframe = self._within_time_window(ev)
            if in_timeframe:
                # update/create in cache
                rec = self._event_cache.get(ev_id)
                if not rec:
                    rec = {"current": None, "versions": []}
                    self._event_cache[ev_id] = rec
                    self._added_to_cache += 1

                # store a snapshot if there's an actual change
                if change_type != "no-change":
                    rec["versions"].append({
                        "timestamp": datetime.utcnow(),
                        "event": ev.copy()
                    })
                    # if old_in_active or if newly meets criteria => changed
                    if old_in_active or self.criteria_func(ev):
                        changed_ids.add(ev_id)

                rec["current"] = ev

                # if newly meets criteria => add to active
                if self.criteria_func(ev) and not old_in_active:
                    self._active_tracking_set.add(ev_id)
                    self._added_to_active_set += 1
                    changed_ids.add(ev_id)

            else:
                # out of timeframe => remove from cache if present
                if old_in_cache:
                    del self._event_cache[ev_id]
                    self._removed_from_cache += 1

                # also remove from active
                if old_in_active:
                    self._active_tracking_set.remove(ev_id)
                    self._removed_from_active_set += 1

            return in_timeframe

    def _describe_change(self, ev: dict) -> dict:
        """
        'deleted' if status=cancelled,
        'created' if not in cache,
        'updated' if in cache and something changed,
        'no-change' if in cache but no fields changed.
        """
        ev_id = ev.get("id", "")
        status = ev.get("status", "")
        rec = self._event_cache.get(ev_id)
        old_event = rec["current"] if rec else {}

        if status == "cancelled":
            diffs = self._compute_diff(old_event, ev)
            change_type = "deleted"
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
        Return shallow diff as {fieldName: {"old": val, "new": val}, ...}
        """
        changes = {}
        all_keys = set(old_event.keys()).union(new_event.keys())
        for k in all_keys:
            if old_event.get(k) != new_event.get(k):
                changes[k] = {"old": old_event.get(k), "new": new_event.get(k)}
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
        now = datetime.utcnow()
        start = now - timedelta(hours=self.time_window_past_hours)
        end = now + timedelta(hours=self.time_window_future_hours)
        return start, end

    def _parse_event_start(self, event: dict) -> Optional[datetime]:
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
        for ev_id, rec in list(self._event_cache.items()):
            current_event = rec["current"]
            if not current_event:
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
        Poll immediately for each calendar, prune out-of-window,
        then rebuild _active_tracking_set using new_criteria_func.
        """
        self.criteria_func = new_criteria_func

        # zero out counters
        self._added_to_cache = 0
        self._removed_from_cache = 0
        self._added_to_active_set = 0
        self._removed_from_active_set = 0

        # 1) Perform a poll (full or incremental) for each calendar
        for cal_id in self.calendar_ids:
            if not self._last_sync_token:
                logger.info(f"[GCalEventChangeAgent] new_criteria_reset => FULL fetch for {cal_id}.")
                await self._handle_full_fetch(cal_id)
            else:
                logger.info(f"[GCalEventChangeAgent] new_criteria_reset => incremental fetch for {cal_id}.")
                await self._handle_incremental_fetch(cal_id)

        # 2) Prune out-of-window
        self.prune_out_of_window_events()

        # 3) Completely reset active set
        old_active_count = len(self._active_tracking_set)
        self._active_tracking_set = set()
        self._removed_from_active_set += old_active_count

        # 4) Re-check each event in cache
        local_added = 0
        for ev_id, rec in self._event_cache.items():
            ev_current = rec.get("current")
            if ev_current and self.criteria_func(ev_current):
                self._active_tracking_set.add(ev_id)
                local_added += 1
        self._added_to_active_set += local_added

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
