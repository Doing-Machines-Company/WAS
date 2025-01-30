# api_agent_classes.py

import enum
from dataclasses import dataclass
from typing import Any, Optional


class APIType(enum.Enum):
    SPECIAL = "special"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"
    CANVAS = "canvas"

    @classmethod
    def from_string(cls, api_str: str) -> "APIType":
        try:
            return cls(api_str.lower())
        except ValueError:
            raise ValueError(
                f"Invalid API type: {api_str}."
                f"Valid options are: {[e.value for e in cls]}"
            )


class APIActionType(enum.Enum):
    """Represents either a special action or one tied to a specific API."""

    # Special
    STOP = "stop"
    REQUEST_USER_INPUT = "request_user_input"

    # Gmail
    GMAIL_LIST_MESSAGES = "gmail_list_messages"
    GMAIL_GET_MESSAGE = "gmail_get_message"
    GMAIL_SEND_EMAIL = "gmail_send_email"
    GMAIL_LIST_LABELS = "gmail_list_labels"

    # Google Calendar
    CALENDAR_LIST_CALENDARS = "calendar_list_calendars"
    CALENDAR_CREATE_EVENT = "calendar_create_event"
    CALENDAR_LIST_EVENTS = "calendar_list_events"
    CALENDAR_UPDATE_EVENT = "calendar_update_event"
    CALENDAR_DELETE_EVENT = "calendar_delete_event"

    # Canvas
    CANVAS_LIST_COURSES = "canvas_list_courses"
    CANVAS_LIST_ASSIGNMENTS = "canvas_list_assignments"
    CANVAS_GET_ASSIGNMENT_DETAILS = "canvas_get_assignment_details"
    CANVAS_LIST_MODULES = "canvas_list_modules"
    CANVAS_GET_MODULE_ITEMS = "canvas_get_module_items"
    CANVAS_GET_GRADES = "canvas_get_grades"
    CANVAS_GET_SUBMISSION_HISTORY = "canvas_get_submission_history"
    CANVAS_LIST_PAGES = "canvas_list_pages"
    CANVAS_GET_PAGE = "canvas_get_page"
    CANVAS_LIST_FILES = "canvas_list_files"
    CANVAS_GET_FILE = "canvas_get_file"
@dataclass
class APILinearMemory:
    """
    Simple record of an API call and response
    used for debug, context, or chain-of-thought logging.
    """

    api_type: APIType
    call: str  # e.g., the API action name or details
    received: str  # e.g., the response from the API call


@dataclass
class APIAction:
    """
    Unified container for an action:
      - action_type: The enumerated type (STOP, REQUEST_USER_INPUT, GMAIL_LIST_MESSAGES, etc.)
      - reason: Why the LLM decided on this action
      - parameters: Dictionary or data with the parameters for the API call
    """

    action_type: APIActionType
    reason: Optional[str] = None
    parameters: Optional[Any] = None
