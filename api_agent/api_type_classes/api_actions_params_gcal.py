# api_actions_params_gcal.py

from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from datetime import datetime

@dataclass
class CalendarListCalendarsParams:
    maxResults: Optional[int] = None
    minAccessRole: Optional[str] = None
    showHidden: Optional[bool] = None

@dataclass
class CalendarCreateEventParams:
    summary: str  # Still required if you want a summary at minimum
    description: Optional[str] = None
    location: Optional[str] = None

    calendarId: str = None

    start: Optional[Union[str, datetime]] = None
    end: Optional[Union[str, datetime]] = None
    timeZone: str = None

    colorId: Optional[str] = None
    transparency: Optional[str] = None
    visibility: Optional[str] = None


@dataclass
class CalendarListEventsParams:
    calendarId: Optional[str] = None  # <-- add this
    maxResults: int = 10
    timeMin: Optional[Union[str, datetime]] = None
    timeMax: Optional[Union[str, datetime]] = None
    singleEvents: bool = True
    orderBy: str = "startTime"
    showDeleted: Optional[bool] = None
    timeZone: Optional[str] = None

@dataclass
class CalendarUpdateEventParams:
    event_id: str
    fields_to_update: Dict[str, Any]
    calendarId: Optional[str] = None

@dataclass
class CalendarDeleteEventParams:
    event_id: str
    calendarId: Optional[str] = None
