# api_actions_params_calendar.py
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class CalendarListCalendarsParams:
    """
    Parameters for listing a user's calendars.
    """
    pass  # For now, no special parameters are needed. Could add 'maxResults' if you wish.

@dataclass
class CalendarCreateEventParams:
    """
    Parameters for creating a calendar event.
    """
    summary: str = "Test Event"
    description: str = "This is a test event."
    location: str = "123 Main St."
    start: datetime = datetime.now()
    end: datetime = datetime.now()
    timeZone: str = "America/New_York"
    # You could also add 'attendees', etc.

@dataclass
class CalendarListEventsParams:
    """
    Parameters for listing upcoming events.
    """
    maxResults: int = 10
    timeMin: Optional[datetime] = None  # If None, we default to now in the code
    singleEvents: bool = True
    orderBy: str = "startTime"

@dataclass
class CalendarUpdateEventParams:
    """
    Parameters for updating a specific event.
    """
    event_id: str
    fields_to_update: Dict[str, Any]  # e.g., {"summary": "New Title"}

@dataclass
class CalendarDeleteEventParams:
    """
    Parameters for deleting an event.
    """
    event_id: str
