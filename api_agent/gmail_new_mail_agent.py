# gmail_new_mail_agent.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Callable, Dict, Any

from googleapiclient.errors import HttpError

from passive_api_agent import PassiveAPIAgent
from api_agent_classes import APIAction, APIActionType
from api_functions import GmailAPIHandler
from api_type_classes.api_actions_params_gmail import GmailGetMessageParams

logger = logging.getLogger(__name__)


class GmailNewMailAgent(PassiveAPIAgent):
    """
    A 'passive' agent that:
      - Caches and tracks threads (not just individual messages).
      - On startup, crawls all threads that have a message within the last X timeframe (timeframe_hours).
      - On each poll:
          * We call the Gmail History API (no label filter) to detect all new messages.
          * If the thread is in our actively tracked set (_active_tracking_set), we fetch changes and fire the callback (no criteria check).
          * Else if the new message's labelIds intersect with self.label_ids, we consider it a newly relevant thread and fetch changes.
          * We skip drafts.
          * If after fetching a new thread it passes our criteria_func, we add that thread to the actively tracked set.
      - We have one callback, on_new_matching_threads, which is triggered:
          1) For threads we are already tracking if they have new changes.
          2) For threads that newly pass the criteria function.
      - On startup or a new criteria reset, we only evaluate the criteria function for threads in the timeframe,
        ignoring older ones for performance reasons.

    Additional new feature:
      - new_criteria_reset(new_criteria_func):
          1) Replaces the agent's criteria_func.
          2) Clears the actively tracked set.
          3) Forces an immediate poll (handle_polling).
          4) Prunes old threads (outside timeframe).
          5) Re-checks the remaining threads in the cache with the new criteria function => track + callback if newly matched.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        gmail_handler: Optional[GmailAPIHandler],
        criteria_func: Callable[[dict], bool],
        timeframe_hours: int = 72,
        label_ids: Optional[List[str]] = None,
        last_history_id: Optional[str] = None
    ):
        super().__init__(check_interval_seconds)
        self.gmail_handler = gmail_handler or GmailAPIHandler()
        self.criteria_func = criteria_func
        self.timeframe_hours = timeframe_hours

        # For newly discovered threads, we only consider them if they appear under these labelIds (e.g. "INBOX")
        self.label_ids = label_ids or ["INBOX"]

        self.last_history_id = last_history_id

        # In-memory cache of thread_id -> thread_resource
        self._thread_cache: Dict[str, dict] = {}

        # Threads that have passed the criteria at least once since last reset
        self._active_tracking_set: set[str] = set()

        # Optional callback for "new or updated" threads
        self.on_tracked_change: Optional[Callable[[List[dict]], None]] = None

    async def start(self):
        """
        1) Initial crawl of recent threads (timeframe_hours)
        2) Prune older threads
        3) Evaluate any leftover threads for the criteria => track them if matched
        4) If we don't have a last_history_id, fetch it
        5) Start the normal PassiveAPIAgent loop
        """
        logger.info("Performing initial crawl of recent threads...")
        self._initial_crawl()

        # Prune older threads so we only keep items in timeframe
        self._prune_old_threads()

        # Evaluate leftover threads for criteria
        newly_matched = []
        for thread_id, thread_data in self._thread_cache.items():
            if thread_id not in self._active_tracking_set:
                if self.criteria_func(thread_data):
                    self._active_tracking_set.add(thread_id)
                    newly_matched.append(thread_data)

        if newly_matched and self.on_tracked_change:
            logger.info(f"Firing callback for {len(newly_matched)} newly matched thread(s) on startup.")
            self.on_tracked_change(newly_matched)

        # If we don't have a baseline, fetch a current historyId so we skip older mail
        if not self.last_history_id:
            hid = self._fetch_current_history_id()
            if hid:
                logger.info(f"GmailNewMailAgent => Setting initial last_history_id to {hid}")
                self.last_history_id = hid

        await super().start()

    async def handle_polling(self):
        """
        Called periodically:
          - Compare new_hid vs. last_history_id
          - If different, gather new messages from the entire mailbox (no label filter)
          - Skip drafts
          - If thread is in active set => fetch, callback
          - Else if thread label intersects with self.label_ids => fetch => if new pass => add + callback
          - Prune old threads not in active set
        """
        new_hid = self._fetch_current_history_id()
        if not new_hid:
            logger.warning("GmailNewMailAgent => could not fetch current historyId.")
            return

        if not self.last_history_id:
            logger.info("GmailNewMailAgent => first run in handle_polling, ignoring older mail.")
            self.last_history_id = new_hid
            return

        if new_hid == self.last_history_id:
            logger.info("GmailNewMailAgent => no new mail.")
            return

        changed_items = self._fetch_changed_ids_for_all(self.last_history_id, new_hid)
        logger.info(f"GmailNewMailAgent => found {len(changed_items)} new/changed message(s).")

        # We track two sets for the callback:
        #  1) already-tracked threads that changed
        #  2) newly matched threads
        changed_tracked_thread_ids = set()
        newly_matched_thread_ids = set()

        for msg_id, label_list in changed_items:
            if "DRAFT" in label_list:
                logger.info(f"Skipping message {msg_id} because it is labeled DRAFT.")
                continue

            # fetch the message to confirm
            try:
                action = APIAction(
                    action_type=APIActionType.GMAIL_GET_MESSAGE,
                    parameters=GmailGetMessageParams(messageId=msg_id).__dict__
                )
                msg_data = self.gmail_handler.perform_action(action)
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"Message {msg_id} not found (404). Skipping.")
                    continue
                else:
                    raise e

            if not msg_data:
                continue

            msg_labels = msg_data.get("labelIds", [])
            if "DRAFT" in msg_labels:
                logger.info(f"Skipping message {msg_id} because it is labeled DRAFT.")
                continue

            thread_id = msg_data.get("threadId")
            if not thread_id:
                continue

            # Decide if we should fetch the thread
            #  - If in active set => always fetch & callback
            #  - Else if label intersection => fetch & check criteria
            if thread_id in self._active_tracking_set:
                # We'll definitely fetch it
                fetch_this_thread = True
            else:
                # Not tracked yet => only fetch if new message intersects label_ids
                if any(lbl in self.label_ids for lbl in label_list):
                    fetch_this_thread = True
                else:
                    fetch_this_thread = False

            if not fetch_this_thread:
                continue

            # Get entire thread
            thread_data = self._fetch_thread_by_id(thread_id)
            if not thread_data:
                continue

            # Update the cache
            self._thread_cache[thread_id] = thread_data

            # If it's already tracked => add to changed set
            if thread_id in self._active_tracking_set:
                changed_tracked_thread_ids.add(thread_id)
            else:
                # Not in tracked set => see if it passes criteria => track it
                if self.criteria_func(thread_data):
                    self._active_tracking_set.add(thread_id)
                    newly_matched_thread_ids.add(thread_id)

        # Prune old threads not in active set
        self._prune_old_threads()

        # Combine sets => trigger callback
        all_updated_ids = changed_tracked_thread_ids.union(newly_matched_thread_ids)
        if all_updated_ids and self.on_tracked_change:
            updated_list = [self._thread_cache[tid] for tid in all_updated_ids]
            self.on_tracked_change(updated_list)

        # Update last_history_id
        self.last_history_id = new_hid

    async def new_criteria_reset(self, new_criteria_func: Callable[[dict], bool]):
        """
        Allows changing the agent's criteria function at runtime:
          1) Update self.criteria_func.
          2) Clear out self._active_tracking_set.
          3) Perform an immediate single poll (handle_polling).
          4) Prune old threads (so we only keep the timeframe).
          5) Re-check the remaining threads in the cache with the new criteria => track them + callback
        """
        logger.info("new_criteria_reset => Setting new criteria function, clearing active tracking set.")
        self.criteria_func = new_criteria_func
        self._active_tracking_set.clear()

        # Step 3: immediate poll
        await self.handle_polling()

        # Step 4: prune old threads
        self._prune_old_threads()

        # Step 5: re-check all remaining threads with new criteria
        newly_matched_thread_ids = set()
        for thread_id, thread_data in self._thread_cache.items():
            # Only check if not already tracked
            if thread_id not in self._active_tracking_set:
                if self.criteria_func(thread_data):
                    self._active_tracking_set.add(thread_id)
                    newly_matched_thread_ids.add(thread_id)

        if newly_matched_thread_ids and self.on_tracked_change:
            updated_list = [self._thread_cache[tid] for tid in newly_matched_thread_ids]
            logger.info(
                f"new_criteria_reset => Found {len(updated_list)} thread(s) matching the new criteria. Firing callback."
            )
            # self.on_tracked_change(updated_list)

    # ------------------------------------------------
    # Internal helpers
    # ------------------------------------------------
    def _fetch_current_history_id(self) -> Optional[str]:
        """
        Retrieve the latest historyId from getProfile().
        """
        try:
            prof = self.gmail_handler.service.users().getProfile(userId='me').execute()
            return prof.get('historyId')
        except Exception as e:
            logger.error(f"Failed to fetch current historyId: {e}")
            return None

    def _fetch_changed_ids_for_all(self, old_hid: str, new_hid: str) -> List[Any]:
        """
        Calls the Gmail history API for 'messageAdded' events across *all* labels (no label filter).
        Returns list of (message_id, label_list).
        """
        all_map = {}
        page_token = None

        while True:
            try:
                resp = self.gmail_handler.service.users().history().list(
                    userId='me',
                    startHistoryId=old_hid,
                    historyTypes=["messageAdded"],
                    pageToken=page_token
                ).execute()

                for record in resp.get('history', []):
                    for added in record.get('messagesAdded', []):
                        msg_obj = added.get('message', {})
                        mid = msg_obj.get('id')
                        labs = msg_obj.get('labelIds', [])
                        if mid:
                            if mid not in all_map:
                                all_map[mid] = set()
                            all_map[mid].update(labs)

                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
            except HttpError as e:
                logger.error(f"Error calling history API: {e}")
                break

        return [(m, list(lbls)) for m, lbls in all_map.items()]

    def _fetch_thread_by_id(self, thread_id: str) -> Optional[dict]:
        """
        Fetches an entire thread object with 'full' message payloads.
        """
        try:
            thread_data = self.gmail_handler.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()
            return thread_data
        except HttpError as e:
            logger.error(f"Could not fetch thread {thread_id}: {e}")
            return None

    def _initial_crawl(self):
        """
        Fetch threads that have at least one message in the last self.timeframe_hours hours,
        via a Gmail query like 'newer_than:Xh'. Store them in _thread_cache.
        """
        query = f"newer_than:{self.timeframe_hours}h"
        page_token = None

        while True:
            resp = self.gmail_handler.service.users().threads().list(
                userId='me',
                q=query,
                pageToken=page_token
            ).execute()

            threads = resp.get('threads', [])
            if not threads:
                break

            for th in threads:
                tid = th.get("id")
                if not tid:
                    continue
                thread_data = self._fetch_thread_by_id(tid)
                if thread_data:
                    self._thread_cache[tid] = thread_data

            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        logger.info(f"_initial_crawl => Found {len(self._thread_cache)} threads so far in last {self.timeframe_hours}h.")

    def _prune_old_threads(self):
        """
        Remove from cache any thread that is NOT in the actively tracked set
        and does not have a message in the last self.timeframe_hours hours.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.timeframe_hours)
        to_remove = []

        for thread_id, thread_data in self._thread_cache.items():
            if thread_id in self._active_tracking_set:
                # If it's in the active set, never prune
                continue
            # Otherwise, check if it's in timeframe
            if not self._thread_in_timeframe(thread_data, cutoff):
                to_remove.append(thread_id)

        for tid in to_remove:
            del self._thread_cache[tid]

        if to_remove:
            logger.info(f"Pruned {len(to_remove)} old threads from cache outside timeframe.")
        else:
            logger.info("No old threads to prune (outside actively tracked).")

    def _thread_in_timeframe(self, thread_data: dict, cutoff: datetime) -> bool:
        """
        Returns True if the thread has at least one message with internalDate >= cutoff.
        """
        messages = thread_data.get("messages", [])
        for msg in messages:
            msg_time = self._gmail_message_internal_datetime(msg)
            if msg_time >= cutoff:
                return True
        return False

    def _gmail_message_internal_datetime(self, message: dict) -> datetime:
        """
        Extract a Python datetime (UTC) from the 'internalDate' field of a Gmail message resource.
        """
        try:
            internal_str = message.get("internalDate")
            if not internal_str:
                return datetime.now(timezone.utc)
            millis = int(internal_str)
            return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
        except:
            return datetime.now(timezone.utc)

    # ------------------------------------------------
    # Public utility
    # ------------------------------------------------
    def get_all_cached_threads(self) -> List[dict]:
        """
        Returns the entire list of cached threads as a list of dicts.
        """
        return list(self._thread_cache.values())

    def get_matching_threads(self) -> List[dict]:
        """
        Returns all threads in our cache that meet the criteria function right now.
        """
        matched = []
        for td in self._thread_cache.values():
            if self.criteria_func(td):
                matched.append(td)
        return matched
