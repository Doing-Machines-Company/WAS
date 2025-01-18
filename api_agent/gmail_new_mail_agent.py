# gmail_new_mail_agent.py

import logging
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Callable, Dict, Any

from googleapiclient.errors import HttpError

from passive_api_agent import PassiveAPIAgent
from api_agent_classes import APIAction, APIActionType
from api_functions import GmailAPIHandler
from api_type_classes.api_actions_params_gmail import GmailGetMessageParams

logger = logging.getLogger(__name__)


def gmail_message_internal_datetime(message: dict) -> datetime:
    """
    Extracts a Python datetime (UTC) from the 'internalDate' field of a Gmail message resource.

    Gmail's 'internalDate' is in milliseconds since epoch as a string.
    Example: "1673982840000"
    """
    # internalDate is a string with millisecond-precision epoch time
    try:
        internal_date_str = message.get("internalDate")
        if not internal_date_str:
            return datetime.now(timezone.utc)

        millis = int(internal_date_str)
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
    except:
        return datetime.now(timezone.utc)


class GmailNewMailAgent(PassiveAPIAgent):
    """
    A 'passive' agent that:
      - Caches and tracks threads (not individual messages).
      - On startup, crawls all threads that have a message within the last X timeframe.
      - On each poll, checks Gmail History for new messages (we skip drafts).
        * If a new message belongs to a thread outside our cache, fetch it and track it.
        * If a new message belongs to a thread in our cache, refetch that thread (to get updated state).
      - We store all threads in a local JSON cache.
      - A user-defined 'criteria_func(thread_dict)' can be applied to each thread.
      - We optionally provide a callback on new or updated threads that match.
      - On startup, we also check all initially loaded threads against the criteria
        and fire the callback for those that match.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        gmail_handler: Optional[GmailAPIHandler],
        criteria_func: Callable[[dict], bool],
        timeframe_hours: int = 72,
        cache_json_path: str = "gmail_threads_cache.json",
        label_ids: Optional[List[str]] = None,
        last_history_id: Optional[str] = None
    ):
        super().__init__(check_interval_seconds)
        self.gmail_handler = gmail_handler or GmailAPIHandler()
        self.criteria_func = criteria_func
        self.timeframe_hours = timeframe_hours
        self.label_ids = label_ids or ["INBOX"]
        self.last_history_id = last_history_id

        # This will store thread_id -> thread_resource (as returned by the Gmail threads.get() call)
        self._thread_cache: Dict[str, dict] = {}

        # Where we store the JSON version of self._thread_cache, along with last_history_id
        self.cache_json_path = cache_json_path

        # Optional callback: called with a list of newly matching threads each time we detect changes
        self.on_new_matching_threads: Optional[Callable[[List[dict]], None]] = None

    async def start(self):
        """
        Overridden to:
          1) Load our existing cache from disk (if present).
          2) Perform the initial crawl of threads in our timeframe.
          3) Prune old threads from the cache.
          4) Save the updated cache.
          5) Check all loaded threads against the criteria function. Fire callback if they match.
          6) Determine the initial last_history_id if not provided.
          7) Then start the normal PassiveAPIAgent loop (polling).
        """
        self._load_cache_from_json()

        # 1) Perform the initial crawl
        logger.info("Performing initial crawl of recent threads...")
        self._initial_crawl()

        # 2) Prune older threads
        self._prune_old_threads()

        # 3) Save changes
        self._save_cache_to_json()

        # 4) Check all loaded threads against criteria and fire callback for matches
        initial_matched = self.get_matching_threads()
        if initial_matched and self.on_new_matching_threads:
            logger.info(f"Firing callback for {len(initial_matched)} thread(s) matching criteria on startup.")
            self.on_new_matching_threads(initial_matched)

        # 5) If we still don't have a last_history_id, get it now so we skip older changes
        if not self.last_history_id:
            hid = self._fetch_current_history_id()
            if hid:
                logger.info(f"GmailNewMailAgent => Setting initial last_history_id to {hid}")
                self.last_history_id = hid

        # 6) Now proceed with normal PassiveAPIAgent loop
        await super().start()

    async def handle_polling(self):
        """
        Called periodically by the parent's main loop:
          - We check if historyId changed.
          - If so, retrieve new messages from that history range.
          - For each new message (that isn't a draft), we get its thread.
          - Update our cache, prune old threads, save, invoke callback for newly matched threads.
        """
        new_hid = self._fetch_current_history_id()
        if not new_hid:
            logger.warning("GmailNewMailAgent => could not fetch current historyId.")
            return

        if not self.last_history_id:
            # If we don't have a baseline, set it and skip historical stuff
            logger.info("GmailNewMailAgent => first run in handle_polling, ignoring older mail.")
            self.last_history_id = new_hid
            return

        if new_hid == self.last_history_id:
            logger.info("GmailNewMailAgent => no new mail.")
            return

        # Fetch newly added message IDs from the history
        changed_items = self._fetch_changed_ids_for_labels(self.last_history_id, new_hid)
        logger.info(f"GmailNewMailAgent => found {len(changed_items)} new/changed message(s).")

        newly_matched_threads = []

        for msg_id, label_list in changed_items:
            # Skip any message with the DRAFT label
            if "DRAFT" in label_list:
                logger.info(f"Skipping message {msg_id} because it is labeled DRAFT.")
                continue

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
                # Some unexpected empty result
                continue

            msg_labels = msg_data.get("labelIds", [])
            if "DRAFT" in msg_labels:
                logger.info(f"Skipping message {msg_id} because it is labeled DRAFT.")
                continue

            thread_id = msg_data.get("threadId")
            if not thread_id:
                continue

            # Fetch the thread, store in cache
            thread_data = self._fetch_thread_by_id(thread_id)
            if not thread_data:
                continue

            self._thread_cache[thread_id] = thread_data

            # Check if thread is in timeframe. If so and it meets criteria, add to newly_matched_threads
            if self._thread_in_timeframe(thread_data) and self.criteria_func(thread_data):
                newly_matched_threads.append(thread_data)

        # Prune old threads from the cache
        self._prune_old_threads()

        # Save changes
        self._save_cache_to_json()

        # Fire callback if new matches
        if newly_matched_threads and self.on_new_matching_threads:
            self.on_new_matching_threads(newly_matched_threads)

        # Update our last_history_id
        self.last_history_id = new_hid

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

    def _fetch_changed_ids_for_labels(self, old_hid: str, new_hid: str) -> List[Any]:
        """
        For each label in self.label_ids, call the Gmail history API with:
            startHistoryId=old_hid
            historyTypes=["messageAdded"]
            labelId=the label
        Collect all added message IDs in a list of (message_id, label_list).
        """
        all_map = {}  # msg_id -> set(labelIds)

        for lbl in self.label_ids:
            page_token = None
            while True:
                try:
                    resp = self.gmail_handler.service.users().history().list(
                        userId='me',
                        startHistoryId=old_hid,
                        historyTypes=["messageAdded"],
                        labelId=lbl,
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
                    logger.error(f"Error calling history API for label={lbl}: {e}")
                    break

        return [(mid, list(labels)) for mid, labels in all_map.items()]

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
        Fetches all threads that have at least one message in the last self.timeframe_hours hours.
        (We do this by building a Gmail query, e.g. 'newer_than:72h').
        Then we fetch the entire thread for each matching item and store it.
        """
        query = f"newer_than:{self.timeframe_hours}h"
        logger.info(f"_initial_crawl => Searching with query: {query}")

        page_token = None
        while True:
            resp = self.gmail_handler.service.users().threads().list(
                userId='me',
                q=query,
                pageToken=page_token
            ).execute()

            threads = resp.get('threads', [])
            for th in threads:
                thread_id = th.get("id")
                if not thread_id:
                    continue

                thread_data = self._fetch_thread_by_id(thread_id)
                if thread_data:
                    self._thread_cache[thread_id] = thread_data

            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        logger.info(f"_initial_crawl => Found {len(self._thread_cache)} threads so far.")

    def _prune_old_threads(self):
        """
        Remove any thread from the cache that does not have at least one message
        in the last self.timeframe_hours hours.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.timeframe_hours)
        to_remove = []
        for thread_id, thread_data in self._thread_cache.items():
            # If the thread is not in timeframe, mark it for removal
            if not self._thread_in_timeframe(thread_data, cutoff):
                to_remove.append(thread_id)

        # Remove them
        for tid in to_remove:
            del self._thread_cache[tid]

        if to_remove:
            logger.info(f"Pruned {len(to_remove)} old threads from cache.")
        else:
            logger.info("No old threads to prune.")

    def _thread_in_timeframe(self, thread_data: dict, cutoff: Optional[datetime] = None) -> bool:
        """
        Returns True if thread_data has at least one message whose internalDate >= cutoff.

        If cutoff is None, we default to now - timeframe_hours.
        """
        if not cutoff:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.timeframe_hours)

        messages = thread_data.get("messages", [])
        for msg in messages:
            msg_time = gmail_message_internal_datetime(msg)
            if msg_time >= cutoff:
                return True
        return False

    def _load_cache_from_json(self):
        """
        Loads self._thread_cache and self.last_history_id from the JSON file (if it exists).
        """
        if not os.path.exists(self.cache_json_path):
            return
        try:
            with open(self.cache_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._thread_cache = data.get("thread_cache", {})
            self.last_history_id = data.get("last_history_id", None)
            logger.info(f"Loaded cache from {self.cache_json_path} with {len(self._thread_cache)} threads.")
        except Exception as e:
            logger.error(f"Error loading cache from {self.cache_json_path}: {e}")

    def _save_cache_to_json(self):
        """
        Saves self._thread_cache and self.last_history_id to the JSON file.
        """
        data = {
            "thread_cache": self._thread_cache,
            "last_history_id": self.last_history_id
        }
        try:
            with open(self.cache_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved cache to {self.cache_json_path} with {len(self._thread_cache)} threads.")
        except Exception as e:
            logger.error(f"Error saving cache to {self.cache_json_path}: {e}")

    def get_all_cached_threads(self) -> List[dict]:
        """
        Returns the entire list of cached threads as a list of dicts.
        """
        return list(self._thread_cache.values())

    def get_matching_threads(self) -> List[dict]:
        """
        Returns only those threads in our cache for which criteria_func(thread_data) == True.
        """
        matched = []
        for td in self._thread_cache.values():
            if self.criteria_func(td):
                matched.append(td)
        return matched
