# supabase_calendar_tasks_params.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

#
# Calendar param classes
#

@dataclass
class SupabaseListCalendarEventsParams:
    """
    Parameters for listing all future calendar events.
    """
    user_id: Optional[str] = None

@dataclass
class SupabaseCreateCalendarEventParams:
    """
    Parameters for creating a new calendar event.
    """
    user_id: str
    name: str
    start: str
    end: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: Optional[Dict[str, Any]] = None

@dataclass
class SupabaseUpdateCalendarEventParams:
    """
    Parameters for updating a calendar event.
    """
    event_id: int
    fields_to_update: Dict[str, Any]
    user_id: Optional[str] = None

@dataclass
class SupabaseDeleteCalendarEventParams:
    """
    Parameters for deleting a calendar event.
    """
    event_id: int
    user_id: Optional[str] = None

#
# Task param classes
#

@dataclass
class SupabaseListTasksParams:
    """
    Parameters for listing future/incomplete tasks.
    """
    user_id: Optional[str] = None

@dataclass
class SupabaseCreateTaskParams:
    """
    Parameters for creating a new task.
    """
    user_id: str
    name: str
    due: Optional[str] = None # Is now optional
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    send_notification: bool = False
    source: Optional[Dict[str, Any]] = None

@dataclass
class SupabaseUpdateTaskParams:
    """
    Parameters for updating a task.
    """
    task_id: int
    fields_to_update: Dict[str, Any]
    user_id: Optional[str] = None

@dataclass
class SupabaseDeleteTaskParams:
    """
    Parameters for deleting a task.
    """
    task_id: int
    user_id: Optional[str] = None
