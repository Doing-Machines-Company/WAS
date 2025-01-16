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
    We store (string_value, is_safe):
      - 'is_safe' = True  => not destructive
      - 'is_safe' = False => destructive / irreversible
    Override __new__ to attach the extra 'is_safe' field.
    """

    def __new__(cls, value: str, is_safe: bool):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.is_safe = is_safe
        return obj

    # Special (non-API) actions
    STOP = ("stop", True)
    REQUEST_USER_INPUT = ("request_user_input", True)

    # Gmail: messages
    GMAIL_LIST_MESSAGES = ("gmail_list_messages", True)
    GMAIL_GET_MESSAGE = ("gmail_get_message", True)
    GMAIL_SEND_EMAIL = ("gmail_send_email", False)  # Irreversible: actually sends mail
    GMAIL_LIST_LABELS = ("gmail_list_labels", True)
    GMAIL_DELETE_MESSAGE = ("gmail_delete_message", False)  # Destructive
    GMAIL_MODIFY_MESSAGE = ("gmail_modify_message", True)

    # Gmail: drafts
    GMAIL_LIST_DRAFTS = ("gmail_list_drafts", True)
    GMAIL_GET_DRAFT = ("gmail_get_draft", True)
    GMAIL_CREATE_DRAFT = ("gmail_create_draft", True)
    GMAIL_UPDATE_DRAFT = ("gmail_update_draft", True)
    GMAIL_DELETE_DRAFT = ("gmail_delete_draft", False)  # destructive for the draft
    GMAIL_SEND_DRAFT = ("gmail_send_draft", False)  # sends the draft => irreversible

    # Google Calendar
    CALENDAR_LIST_CALENDARS = ("calendar_list_calendars", True)
    CALENDAR_CREATE_EVENT = ("calendar_create_event", False)
    CALENDAR_LIST_EVENTS = ("calendar_list_events", True)
    CALENDAR_UPDATE_EVENT = ("calendar_update_event", True)
    CALENDAR_DELETE_EVENT = ("calendar_delete_event", False)

    # Google Tasks
    # Tasklists
    TASKS_LIST_TASKLISTS = ("tasks_list_tasklists", True)
    TASKS_GET_TASKLIST = ("tasks_get_tasklist", True)
    TASKS_CREATE_TASKLIST = ("tasks_create_tasklist", False)
    TASKS_UPDATE_TASKLIST = ("tasks_update_tasklist", True)
    TASKS_DELETE_TASKLIST = ("tasks_delete_tasklist", False)

    # Tasks
    TASKS_LIST_TASKS = ("tasks_list_tasks", True)
    TASKS_GET_TASK = ("tasks_get_task", True)
    TASKS_CREATE_TASK = ("tasks_create_task", False)
    TASKS_UPDATE_TASK = ("tasks_update_task", True)
    TASKS_DELETE_TASK = ("tasks_delete_task", False)
    TASKS_CLEAR_COMPLETED_TASKS = ("tasks_clear_completed_tasks", False)
    TASKS_MOVE_TASK = ("tasks_move_task", True)


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
        If the action is not destructive => True
        If destructive => False
        """
        return self.action_type.is_safe
