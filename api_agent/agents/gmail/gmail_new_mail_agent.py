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

"""

THIS IS VERY IMPORTANT, THE BEHAVIOR OF THIS SCRIPT IS BROKEN

Deleted emails currently aren't being updated and parsed out of the event cache correctly.

"""
class GmailNewMailAgent(PassiveAPIAgent):
    """
    A 'passive' agent that:
      - Caches and tracks threads (not just individual messages).
      - On the first poll, crawls all threads that have a message
        within the last X timeframe (timeframe_hours).
      - On each poll:
          * We call the Gmail History API (no label filter) to detect new messages.
          * We skip drafts.
          * If the thread is in our actively tracked set => fetch & mark as changed
          * Else if new message's labelIds intersect with self.label_ids => fetch => if pass => track
          * Then prune old threads if not in the active set.
      - We have one callback, on_tracked_change, which receives:
          * A dictionary of all active threads,
          * Each entry has "data": <thread_data> and "just_changed": bool
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

        # For newly discovered threads, we only consider them if they appear
        # under these labelIds (e.g. "INBOX")
        self.label_ids = label_ids or ["INBOX"]

        self.last_history_id = last_history_id

        # In-memory cache of thread_id -> thread_resource
        self._thread_cache: Dict[str, dict] = {}

        # Threads that have passed the criteria at least once
        self._active_tracking_set: set[str] = set()

        # Optional callback for "new or updated" threads
        # Now always takes a dictionary keyed by thread_id
        # containing {"data": <thread_data>, "just_changed": bool}
        self.on_tracked_change: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        # For first-run detection in handle_polling
        self._did_initial_crawl = False

    async def handle_polling(self):
        """
        Called periodically:
          1) If first run:
             - Do the initial crawl of recent threads,
             - Prune older threads,
             - Evaluate them for criteria => add to active if matched,
             - Possibly set last_history_id if not set.
             - Mark self._did_initial_crawl = True
          2) Else do incremental polling via Gmail History API
             - Skip drafts
             - If thread is in active => fetch => mark changed
             - Else if new message's labels intersect => fetch => check criteria
          3) Prune old threads not in active set
          4) Fire the callback with the entire active set, tagging which changed
        """
        changed_ids = set()

        if not self._did_initial_crawl:
            logger.info("GmailNewMailAgent => Performing initial crawl of recent threads...")
            self._initial_crawl()
            self._prune_old_threads()

            # Evaluate leftover threads for criteria
            newly_matched = []
            for thread_id, thread_data in self._thread_cache.items():
                if thread_id not in self._active_tracking_set:
                    if self.criteria_func(thread_data):
                        self._active_tracking_set.add(thread_id)
                        newly_matched.append(thread_id)

            # Mark those newly matched as changed
            changed_ids.update(newly_matched)

            # If we don't have a baseline history ID, fetch it to skip older mail
            if not self.last_history_id:
                hid = self._fetch_current_history_id()
                if hid:
                    logger.info(f"GmailNewMailAgent => Setting initial last_history_id to {hid}")
                    self.last_history_id = hid

            self._did_initial_crawl = True
        else:
            # Incremental poll
            new_hid = self._fetch_current_history_id()
            if not new_hid:
                logger.warning("GmailNewMailAgent => could not fetch current historyId.")
            elif not self.last_history_id:
                # first time in handle_polling, but we did do _initial_crawl =>
                # just set last_history_id to new_hid
                logger.info("GmailNewMailAgent => no existing last_history_id, setting it now.")
                self.last_history_id = new_hid
            elif new_hid == self.last_history_id:
                logger.info("GmailNewMailAgent => no new mail since last poll.")
            else:
                # there's new mail
                changed_messages = self._fetch_changed_ids_for_all(self.last_history_id, new_hid)
                logger.info(f"GmailNewMailAgent => found {len(changed_messages)} new/changed message(s).")

                for msg_id, label_list in changed_messages:
                    if "DRAFT" in label_list:
                        # skip
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

                    # skip if draft
                    msg_labels = msg_data.get("labelIds", [])
                    if "DRAFT" in msg_labels:
                        continue

                    thread_id = msg_data.get("threadId")
                    if not thread_id:
                        continue

                    # Decide if we should fetch the thread
                    if thread_id in self._active_tracking_set:
                        fetch_this_thread = True
                    else:
                        # Not tracked => only fetch if it belongs to a label of interest
                        if any(lbl in self.label_ids for lbl in label_list):
                            fetch_this_thread = True
                        else:
                            fetch_this_thread = False

                    if not fetch_this_thread:
                        continue

                    # retrieve the entire thread
                    thread_data = self._fetch_thread_by_id(thread_id)
                    if not thread_data:
                        continue

                    # update the cache
                    self._thread_cache[thread_id] = thread_data

                    # if already in active => mark changed
                    if thread_id in self._active_tracking_set:
                        changed_ids.add(thread_id)
                    else:
                        # newly see if it passes
                        if self.criteria_func(thread_data):
                            self._active_tracking_set.add(thread_id)
                            changed_ids.add(thread_id)

                # update last_history_id
                self.last_history_id = new_hid

            # prune old threads not in active
            self._prune_old_threads()

        # End-of-poll callback: entire active set
        if self.on_tracked_change:
            payload = {}
            for tid in self._active_tracking_set:
                payload[tid] = {
                    "data": self._thread_cache[tid],
                    "just_changed": (tid in changed_ids)
                }
            self.on_tracked_change(payload)

    async def new_criteria_reset(self, new_criteria_func: Callable[[dict], bool]):
        """
        1) Update criteria_func
        2) Clear _active_tracking_set
        3) Force an immediate poll (handle_polling)
        4) Prune old threads
        5) Re-check remaining threads in cache with new criteria => track & mark changed
        """
        logger.info("GmailNewMailAgent => new_criteria_reset: updating criteria, clearing active set.")
        self.criteria_func = new_criteria_func
        self._active_tracking_set.clear()

        # immediate poll
        await self.handle_polling()

        # prune
        self._prune_old_threads()

        # re-check
        changed_ids = set()
        for thread_id, thread_data in self._thread_cache.items():
            if thread_id not in self._active_tracking_set:
                if self.criteria_func(thread_data):
                    self._active_tracking_set.add(thread_id)
                    changed_ids.add(thread_id)

        if self.on_tracked_change and changed_ids:
            payload = {}
            for tid in self._active_tracking_set:
                payload[tid] = {
                    "data": self._thread_cache[tid],
                    "just_changed": (tid in changed_ids)
                }
            logger.info(
                f"GmailNewMailAgent => new_criteria_reset => Found {len(changed_ids)} newly matched thread(s)."
            )
            self.on_tracked_change(payload)

    # ------------------------------------------------
    # Internal helpers
    # ------------------------------------------------
    def _fetch_current_history_id(self) -> Optional[str]:
        """Retrieve the latest historyId from getProfile()."""
        try:
            prof = self.gmail_handler.service.users().getProfile(userId='me').execute()
            return prof.get('historyId')
        except Exception as e:
            logger.error(f"Failed to fetch current historyId: {e}")
            return None

    def _fetch_changed_ids_for_all(self, old_hid: str, new_hid: str) -> List[Any]:
        """
        Calls the Gmail history API for 'messageAdded' events across *all* labels.
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
        """Fetch entire thread with 'full' message payloads."""
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
        via Gmail query 'newer_than:Xh'. Store them in _thread_cache.
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

        logger.info(f"_initial_crawl => Found {len(self._thread_cache)} threads in last {self.timeframe_hours}h.")

    def _prune_old_threads(self):
        """
        Remove from cache any thread that is NOT in the actively tracked set
        and does not have a message in the last self.timeframe_hours hours.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.timeframe_hours)
        to_remove = []

        for thread_id, thread_data in self._thread_cache.items():
            if thread_id in self._active_tracking_set:
                continue  # never prune actively tracked
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
