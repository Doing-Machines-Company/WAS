import time
import logging
from typing import Optional, List, Callable

from passive_api_agent import PassiveAPIAgent
from api_functions import GmailAPIHandler
from api_agent_classes import APIAction, APIActionType
from api_type_classes.api_actions_params_gmail import GmailGetMessageParams
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GmailNewMailAgent(PassiveAPIAgent):
    """
    A passive agent that:
      1) Periodically checks the Gmail History API for newly 'messageAdded' events
         restricted to one or more Gmail labels,
      2) Optionally starts from a user-provided last_history_id (else ignores older mail on first run),
      3) For each new message, retrieves it and applies a user-supplied criteria_func,
      4) Stores matching messages, and can invoke an on_new_mails callback for immediate access.

    This version avoids the "Invalid label value in query" by making a separate History API call
    for each label and merging the results.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        gmail_handler: Optional[GmailAPIHandler],
        criteria_func: Callable[[dict], bool],
        label_ids: Optional[List[str]] = None,
        last_history_id: Optional[str] = None
    ):
        """
        :param check_interval_seconds: Interval (in seconds) to poll for new mail.
        :param gmail_handler: A GmailAPIHandler instance (if None, create a new one).
        :param criteria_func: A function taking a message dict -> bool for matching criteria.
        :param label_ids: One or more Gmail label IDs. Defaults to ["INBOX"] if not specified.
        :param last_history_id: If provided, the agent starts from this history ID 
                                rather than ignoring older mail.
        """
        super().__init__(check_interval_seconds=check_interval_seconds)
        self.gmail_handler = gmail_handler or GmailAPIHandler()
        self.criteria_func = criteria_func
        self.label_ids = label_ids or ["INBOX"]
        self.last_history_id: Optional[str] = last_history_id  # If None, we get it on first run

        self._matching_mails: List[dict] = []  # All matched messages so far
        self.on_new_mails: Optional[Callable[[List[dict]], None]] = None  # Callback for new matches

    async def check_condition(self) -> bool:
        """
        Called every X seconds:
          - Fetch the current historyId from getProfile().
          - If self.last_history_id is None, store the current ID and ignore older mail (first run).
          - Else, if new_history != old_history => condition is True (new mail or changes).
        """
        new_history_id = self._fetch_current_history_id()
        if not new_history_id:
            logger.warning("GmailNewMailAgent => Could not fetch current historyId.")
            return False

        # If we have no saved historyId, set it now (ignore older mail)
        if not self.last_history_id:
            self.last_history_id = new_history_id
            logger.info("GmailNewMailAgent => first run, ignoring older mail.")
            return False

        # If the historyId changed => new mail or label changes
        if new_history_id != self.last_history_id:
            logger.info(f"GmailNewMailAgent => new mail detected. old={self.last_history_id}, new={new_history_id}")
            return True

        logger.info("GmailNewMailAgent => no new mail.")
        return False

    async def perform_actions(self):
        """
        If condition is True => fetch newly 'messageAdded' between old_history_id and new_history_id
        for each label in label_ids, combine unique message IDs, retrieve them, and apply criteria_func.
        """
        old_history = self.last_history_id
        new_history = self._fetch_current_history_id()
        if not old_history or not new_history:
            return

        changed_msg_ids = self._fetch_changed_message_ids(old_history, new_history)
        logger.info(
            f"GmailNewMailAgent => Found {len(changed_msg_ids)} new message(s) since historyId={old_history}."
        )

        iteration_new_matches = []
        for msg_id in changed_msg_ids:
            get_msg_action = APIAction(
                action_type=APIActionType.GMAIL_GET_MESSAGE,
                parameters=GmailGetMessageParams(
                    userId="me",
                    messageId=msg_id,
                    format="full"
                ).__dict__
            )

            # Attempt to retrieve the message
            try:
                msg_details = self.gmail_handler.perform_action(get_msg_action)
            except HttpError as http_err:
                status_code = http_err.resp.status
                if status_code == 404:
                    logger.warning(f"Message {msg_id} not found (404). Possibly deleted or moved.")
                    continue
                else:
                    logger.error(f"Error retrieving message {msg_id}: {http_err}")
                    continue

            # Check if this message meets user criteria
            if msg_details and self.criteria_func(msg_details):
                logger.info(f"Message {msg_id} met criteria. Storing.")
                iteration_new_matches.append(msg_details)

        self._matching_mails.extend(iteration_new_matches)

        # If new matches AND we have a callback => notify the main loop immediately
        if iteration_new_matches and self.on_new_mails:
            self.on_new_mails(iteration_new_matches)

        self.last_history_id = new_history

    def _fetch_current_history_id(self) -> Optional[str]:
        """
        Retrieves the latest 'historyId' via getProfile. Returns None if error.
        """
        try:
            profile = self.gmail_handler.service.users().getProfile(userId='me').execute()
            return profile.get('historyId')
        except Exception as e:
            logger.error(f"Failed to fetch current historyId: {e}")
            return None

    def _fetch_changed_message_ids(self, old_history_id: str, new_history_id: str) -> List[str]:
        """
        Calls the Gmail History API for each label in self.label_ids (one call per labelId) 
        to find newly 'messageAdded' between old_history_id and new_history_id.
        Then merges the resulting message IDs into a set (avoids duplicates if a message 
        has multiple labels).
        """
        all_msg_ids = set()

        for label in self.label_ids:
            page_token = None

            try:
                while True:
                    response = self.gmail_handler.service.users().history().list(
                        userId='me',
                        startHistoryId=old_history_id,
                        historyTypes=["messageAdded"],
                        labelId=label,  # single labelId param => no bracketed list
                        pageToken=page_token
                    ).execute()

                    history_list = response.get('history', [])
                    for history_item in history_list:
                        for added_obj in history_item.get('messagesAdded', []):
                            msg_obj = added_obj.get('message')
                            if msg_obj and 'id' in msg_obj:
                                all_msg_ids.add(msg_obj['id'])

                    page_token = response.get('nextPageToken')
                    if not page_token:
                        break

            except HttpError as e:
                logger.error(
                    "Error while fetching changed message IDs via Gmail History API. "
                    "Possibly startHistoryId is invalid or too old.\n"
                    f"Exception: {e}"
                )

        return list(all_msg_ids)

    def get_matching_mails(self) -> List[dict]:
        """
        Return all messages that have matched so far (for all time).
        """
        return self._matching_mails
