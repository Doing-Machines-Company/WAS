from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class CalendarListCalendarsParams:
    """
    Parameters for listing a user's calendars.
    """
    maxResults: Optional[int] = None
    minAccessRole: Optional[str] = None
    showHidden: Optional[bool] = None


@dataclass
class CalendarCreateEventParams:
    """
    Parameters for creating a calendar event.
    """
    summary: str
    description: str
    location: str
    start: datetime
    end: datetime
    timeZone: str = "America/New_York"

    # Optional extras
    colorId: Optional[str] = None
    transparency: Optional[str] = None
    visibility: Optional[str] = None
    # e.g. recurrence: Optional[List[str]] = None
    # e.g. attendees: Optional[List[dict]] = None


@dataclass
class CalendarListEventsParams:
    """
    Parameters for listing upcoming events.
    """
    maxResults: int = 10
    timeMin: Optional[datetime] = None
    timeMax: Optional[datetime] = None
    singleEvents: bool = True
    orderBy: str = "startTime"

    # Additional optional fields
    showDeleted: Optional[bool] = None
    timeZone: Optional[str] = None


@dataclass
class CalendarUpdateEventParams:
    """
    Parameters for updating a specific event.
    """
    event_id: str
    fields_to_update: Dict[str, Any]


@dataclass
class CalendarDeleteEventParams:
    """
    Parameters for deleting an event.
    """
    event_id: str
