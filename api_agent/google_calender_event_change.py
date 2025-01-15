# google_calender_event_change.py

import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any

from googleapiclient.errors import HttpError

from passive_api_agent import PassiveAPIAgent
from api_agent_classes import APIAction, APIActionType
from api_functions import GoogleCalendarAPIHandler

logger = logging.getLogger(__name__)

class GCalEventChangeAgent(PassiveAPIAgent):
    """
    A 'passive' agent that polls Google Calendar for changes to events
    using the incremental sync approach (syncToken).

    We store:
      - _matching_events: events that meet criteria_func.
      - _all_changes: descriptions of all changed items (including deletions).
      - _event_cache: full data of previously seen events to detect diffs.

    On the first run, we do a full fetch, but do NOT label pre-existing events
    as 'created' or 'updated'. Then, if any of those events are modified later,
    we label them 'updated' and generate a field-by-field diff of changes.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        calendar_handler: Optional[GoogleCalendarAPIHandler],
        criteria_func: Callable[[dict], bool],
        calendar_ids: Optional[List[str]] = None,
        last_sync_token: Optional[str] = None
    ):
        super().__init__(check_interval_seconds)
        self.calendar_handler = calendar_handler or GoogleCalendarAPIHandler()
        self.criteria_func = criteria_func
        self.calendar_ids = calendar_ids or ["primary"]
        self._last_sync_token = last_sync_token

        # Where we store events that matched criteria_func
        self._matching_events: List[dict] = []

        # Where we store info about ALL incremental changes (including deletions)
        self._all_changes: List[dict] = []

        # Cache of event_id -> full event data
        # used for detecting "created/updated" and building a diff
        self._event_cache: Dict[str, dict] = {}

        # Optional callback
        self.on_new_events: Optional[Callable[[List[dict]], None]] = None

    async def handle_polling(self):
        """
        Periodically check for changes in each calendar using incremental sync.
        """
        for cal_id in self.calendar_ids:
            logger.info(f"GCalEventChangeAgent => Checking calendar '{cal_id}'...")

            if not self._last_sync_token:
                # First run => do a full fetch to build initial cache (no "changes" yet).
                logger.info("GCalEventChangeAgent => First run, performing full fetch (no sync token).")
                new_items = await self._handle_first_run(cal_id)
            else:
                logger.info(f"GCalEventChangeAgent => Using syncToken {self._last_sync_token}")
                new_items = await self._handle_incremental_run(cal_id)

            # If we got new matching items, invoke callback
            if new_items and self.on_new_events:
                self.on_new_events(new_items)

            # Add them to the matching events list
            self._matching_events.extend(new_items)

    async def _handle_first_run(self, cal_id: str) -> List[dict]:
        """
        Perform a full fetch of the calendar, store those events in the cache,
        but do NOT label them as created/updated. They existed before we started.
        """
        new_items = []
        try:
            # Full fetch with ordering if you want:
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                orderBy="updated"  # Allowed only before we have a syncToken
            ).execute()
        except HttpError as e:
            logger.error(f"GCalEventChangeAgent => HttpError during first-run fetch: {e}")
            return new_items

        items = resp.get("items", [])
        for ev in items:
            ev_id = ev.get("id")
            if not ev_id:
                continue
            # Store the entire event in the cache as "existing"
            self._event_cache[ev_id] = ev

            # Optionally check if it meets criteria now
            if self.criteria_func(ev):
                new_items.append(ev)

        # Store sync token for next run
        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

        logger.info(
            f"GCalEventChangeAgent => First run complete. Fetched {len(items)} existing events from '{cal_id}'. "
            "These are considered 'pre-existing' so not labeled as created/updated."
        )
        return new_items

    async def _handle_incremental_run(self, cal_id: str) -> List[dict]:
        """
        Use the stored syncToken to do an incremental fetch.
        Each item is described as created/updated/deleted based on our cache.
        """
        new_items = []
        try:
            # Must NOT set a non-default orderBy with syncToken
            resp = self.calendar_handler.service.events().list(
                calendarId=cal_id,
                singleEvents=True,
                syncToken=self._last_sync_token
            ).execute()
        except HttpError as e:
            if e.resp.status == 410:
                logger.warning("GCalEventChangeAgent => Sync token expired/invalid (410). Resetting token.")
                self._last_sync_token = None
                return []
            else:
                logger.error(f"GCalEventChangeAgent => HttpError during incremental fetch: {e}")
                return []

        items = resp.get("items", [])
        logger.info(f"GCalEventChangeAgent => Found {len(items)} changed event(s) for '{cal_id}'.")

        changes_this_round = []
        for ev in items:
            change_description = self._describe_change(ev)
            changes_this_round.append(change_description)

            logger.info(
                f"GCalEventChangeAgent => Change for event_id={change_description['id']}, "
                f"change_type={change_description['change_type']}, diffs={change_description['diffs']}"
            )

            # If event is not "cancelled" and meets criteria, we track it as "new" for this poll
            if self.criteria_func(ev):
                new_items.append(ev)

        self._all_changes.extend(changes_this_round)

        # Update sync token
        nxt = resp.get("nextSyncToken")
        if nxt:
            self._last_sync_token = nxt

        logger.info(f"GCalEventChangeAgent => Found {len(new_items)} matching event(s) for '{cal_id}'.")
        return new_items

    def _describe_change(self, ev: dict) -> dict:
        """
        Determine if the event is 'created', 'updated', or 'deleted' by comparing to our cache.
        Also compute a field-by-field diff of what changed (if anything).
        """
        ev_id = ev.get("id", "")
        kind = ev.get("kind", "")         # typically "calendar#event"
        status = ev.get("status", "")     # "confirmed", "cancelled", etc.

        old_event = self._event_cache.get(ev_id, {})
        if status == "cancelled":
            # A "cancelled" event means a deletion
            change_type = "deleted"
            diffs = self._compute_diff(old_event, ev)
        else:
            if not old_event:
                # The agent hasn't seen this event before => new since agent started
                change_type = "created"
                diffs = self._compute_diff({}, ev)
            else:
                # Check if something actually changed
                diffs = self._compute_diff(old_event, ev)
                if len(diffs) > 0:
                    change_type = "updated"
                else:
                    change_type = "no-change"

        # Update the event cache with the new version of the event (if not "deleted")
        self._event_cache[ev_id] = ev

        return {
            "id": ev_id,
            "change_type": change_type,
            "item_type": kind,
            "status": status,
            "diffs": diffs,  # a dict of fields that changed => {"old": x, "new": y}
        }

    def _compute_diff(self, old_event: dict, new_event: dict) -> dict:
        """
        Compare old_event vs new_event, returning a shallow dict of changed fields:
          {
            "summary": {"old": "Old summary", "new": "New summary"},
            "location": {"old": None, "new": "NYC Office"},
            ...
          }
        """
        changes = {}
        # We'll do a shallow compare for all keys
        all_keys = set(old_event.keys()).union(new_event.keys())
        for k in all_keys:
            old_val = old_event.get(k)
            new_val = new_event.get(k)
            if old_val != new_val:
                changes[k] = {"old": old_val, "new": new_val}
        return changes

    def get_matching_events(self) -> List[dict]:
        """Return all events (including from the first run) that pass criteria_func."""
        return self._matching_events

    def get_all_changes(self) -> List[dict]:
        """Return a list describing all incremental changes observed (excludes the first-run cache)."""
        return self._all_changes
