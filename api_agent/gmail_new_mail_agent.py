# gmail_new_mail_agent.py

import logging
from typing import Optional, List, Callable, Tuple

from googleapiclient.errors import HttpError

from passive_api_agent import PassiveAPIAgent
from api_agent_classes import APIAction, APIActionType
from api_functions import GmailAPIHandler
from api_type_classes.api_actions_params_gmail import (
    GmailGetMessageParams,
    GmailGetDraftParams
)

logger = logging.getLogger(__name__)

class GmailNewMailAgent(PassiveAPIAgent):
    """
    A 'passive' agent that polls Gmail's History API for newly added messages/drafts
    in specified labels.
    If label set includes "DRAFT", we call GMAIL_GET_DRAFT; otherwise GMAIL_GET_MESSAGE.
    """

    def __init__(
        self,
        check_interval_seconds: int,
        gmail_handler: Optional[GmailAPIHandler],
        criteria_func: Callable[[dict], bool],
        label_ids: Optional[List[str]] = None,
        last_history_id: Optional[str] = None
    ):
        super().__init__(check_interval_seconds)
        self.gmail_handler = gmail_handler or GmailAPIHandler()
        self.criteria_func = criteria_func
        self.label_ids = label_ids or ["INBOX"]
        self.last_history_id = last_history_id
        self._matching_mails: List[dict] = []
        self.on_new_mails: Optional[Callable[[List[dict]], None]] = None

    async def handle_polling(self):
        """
        Combines the logic of:
          - checking if historyId changed,
          - if so, fetching new items,
          - retrieving them as message or draft,
          - applying criteria_func,
          - storing matches.
        """
        new_hid = self._fetch_current_history_id()
        if not new_hid:
            logger.warning("GmailNewMailAgent => could not fetch current historyId.")
            return

        # If we never had a last_history_id, skip older mail
        if not self.last_history_id:
            self.last_history_id = new_hid
            logger.info("GmailNewMailAgent => first run, ignoring older mail.")
            return

        if new_hid != self.last_history_id:
            logger.info(f"GmailNewMailAgent => history change detected. old={self.last_history_id}, new={new_hid}")
            changed_items = self._fetch_changed_ids_for_labels(self.last_history_id, new_hid)
            logger.info(f"GmailNewMailAgent => found {len(changed_items)} new item(s).")

            iteration_new = []
            for msg_id, label_list in changed_items:
                if "DRAFT" in label_list:
                    # It's a draft
                    action = APIAction(
                        action_type=APIActionType.GMAIL_GET_DRAFT,
                        parameters=GmailGetDraftParams(draftId=msg_id).__dict__
                    )
                    logger.info(f"GmailNewMailAgent => DRAFT detected with {msg_id}")
                else:
                    # It's a normal message
                    action = APIAction(
                        action_type=APIActionType.GMAIL_GET_MESSAGE,
                        parameters=GmailGetMessageParams(messageId=msg_id).__dict__
                    )

                # ---- NEW: Catch ephemeral or missing items
                # NEEDS TO BE THOUGHT ABOUT BETTER, though it won't matter for MVP
                # I have no clue why we would ever need to check info about an ephemeral draft anyways
                try:
                    result = self.gmail_handler.perform_action(action)
                except HttpError as e:
                    if e.resp.status == 404:
                        logger.warning(
                            f"Item {msg_id} could not be retrieved (404). "
                            "Likely an ephemeral or removed draft/message. Skipping."
                        )
                        continue
                    else:
                        raise e
                # ---- end new logic

                # If we did retrieve it, check if it meets criteria
                if result and self.criteria_func(result):
                    iteration_new.append(result)

            self._matching_mails.extend(iteration_new)
            if iteration_new and self.on_new_mails:
                self.on_new_mails(iteration_new)

            self.last_history_id = new_hid
        else:
            logger.info("GmailNewMailAgent => no new mail/drafts.")

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

    def _fetch_changed_ids_for_labels(self, old_hid: str, new_hid: str) -> List[Tuple[str, List[str]]]:
        """
        We do one call per label in self.label_ids, each time specifying:
          - startHistoryId=old_hid
          - historyTypes=["messageAdded"]
          - labelId=the label
        We gather all items in a dict: msg_id -> set of labelIds
        Then convert to a list of (msg_id, label_list).
        """

        all_map = {}  # msg_id => set(labelIds)

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

                    logger.info(f"GmailNewMailAgent => Here is the response {resp}")

                    # Parse
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

        # Return as list of (msg_id, label_list)
        return [(mid, list(labels)) for mid, labels in all_map.items()]

    def get_matching_mails(self) -> List[dict]:
        return self._matching_mails
