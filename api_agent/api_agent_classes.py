# api_agent_classes.py

import enum
from dataclasses import dataclass
from typing import Optional, Any

class APIType(enum.Enum):
    SPECIAL = "special"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"

    @classmethod
    def from_string(cls, api_str: str) -> 'APIType':
        """
        Converts a string (like "gmail") into the corresponding APIType enum.
        Raises ValueError if the string doesn't match a valid enum member.
        """
        try:
            return cls(api_str.lower())
        except ValueError:
            raise ValueError(
                f"Invalid API type: {api_str}. "
                f"Valid options are: {[e.value for e in cls]}"
            )

class APIActionType(enum.Enum):
    """
    An Enum storing both a string value and a boolean 'is_safe' to indicate
    irreversible (or destructive) actions.
    Override __new__ to attach the extra 'is_safe' field.
    """

    def __new__(cls, value: str, is_safe: bool):
        obj = object.__new__(cls)
        obj._value_ = value      # Store the string (e.g., "gmail_delete_message") as the enum value
        obj.is_safe = is_safe    # Custom attribute
        return obj

    # Special (non-API) actions
    STOP = ("stop", False)
    REQUEST_USER_INPUT = ("request_user_input", False)

    # Gmail actions
    GMAIL_LIST_MESSAGES = ("gmail_list_messages", False)
    GMAIL_GET_MESSAGE = ("gmail_get_message", False)
    GMAIL_SEND_EMAIL = ("gmail_send_email", True)       # Irreversible: sends mail
    GMAIL_LIST_LABELS = ("gmail_list_labels", False)
    GMAIL_DELETE_MESSAGE = ("gmail_delete_message", True)  # Destructive
    GMAIL_MODIFY_MESSAGE = ("gmail_modify_message", False) # E.g. labeling isn't destructive

    # Google Calendar actions
    CALENDAR_LIST_CALENDARS = ("calendar_list_calendars", False)
    CALENDAR_CREATE_EVENT = ("calendar_create_event", True)
    CALENDAR_LIST_EVENTS = ("calendar_list_events", False)
    CALENDAR_UPDATE_EVENT = ("calendar_update_event", False)
    CALENDAR_DELETE_EVENT = ("calendar_delete_event", True)

@dataclass
class APILinearMemory:
    """
    Simple record of an API call and response for debugging, context,
    or chain-of-thought logging.
    """
    api_type: APIType
    call: str          # e.g., the API action name or details
    received: str      # e.g., the response from the API call

@dataclass
class APIAction:
    """
    Unified container for an action decided by an LLM:
      - action_type: The enumerated action type (STOP, GMAIL_LIST_MESSAGES, GMAIL_DELETE_MESSAGE, etc.)
      - reason: Why the LLM decided on this action
      - parameters: Arbitrary data with the parameters for the API call
    """
    action_type: APIActionType
    reason: Optional[str] = None
    parameters: Optional[Any] = None

    @property
    def is_safe(self) -> bool:
        """
        Shortcut property to reveal whether this action is potentially destructive
        (true if the enum's is_safe == True).
        """
        return self.action_type.is_safe
