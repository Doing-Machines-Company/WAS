# api_actions_params_gmail.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class GmailListMessagesParams:
    """
    Parameters for the GMAIL_LIST_MESSAGES action.
    e.g., only 'userId' and an optional 'labelId' to filter messages.
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
    # Optionally add cc, bcc, attachments, etc.

@dataclass
class GmailListLabelsParams:
    """
    Parameters for the GMAIL_LIST_LABELS action.
    """
    userId: str = "me"
