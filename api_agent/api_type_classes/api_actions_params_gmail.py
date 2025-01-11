# api_actions_params_gmail.py
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class GmailListMessagesParams:
    """
    Parameters for the GMAIL_LIST_MESSAGES action.
    e.g., 'userId' and an optional 'labelId' to filter messages.
    """
    userId: str = "me"
    labelId: Optional[str] = None

@dataclass
class GmailGetMessageParams:
    """
    Parameters for the GMAIL_GET_MESSAGE action.
    """
    userId: str = "me"
    messageId: str = "-1"
    format: Optional[str] = None  # e.g., 'full', 'raw', etc.

@dataclass
class GmailSendEmailParams:
    """
    Parameters for the GMAIL_SEND_EMAIL action.
    """
    userId: str = "me"
    to: str = "recipient@example.com"
    subject: str = "Test Email"
    body: str = "This is a test email."

@dataclass
class GmailListLabelsParams:
    """
    Parameters for the GMAIL_LIST_LABELS action.
    """
    userId: str = "me"

@dataclass
class GmailDeleteMessageParams:
    """
    Parameters for the GMAIL_DELETE_MESSAGE action.
    """
    userId: str = "me"
    messageId: str = ""

@dataclass
class GmailModifyMessageParams:
    """
    Parameters for the GMAIL_MODIFY_MESSAGE action, e.g. to label or unlabel a message.
    """
    userId: str = "me"
    messageId: str = ""
    addLabelIds: Optional[List[str]] = None
    removeLabelIds: Optional[List[str]] = None
