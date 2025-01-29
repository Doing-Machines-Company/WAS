# api_actions_params_gtasks.py

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

"""
Define only the parameter dataclasses for Google Tasks actions.
We will *not* redefine the calendar param classes here.
"""

@dataclass
class TasksListTasklistsParams:
    maxResults: Optional[int] = None
    # e.g., pageToken or other optional fields as needed

@dataclass
class TasksGetTasklistParams:
    tasklist_id: str

@dataclass
class TasksCreateTasklistParams:
    title: str

@dataclass
class TasksUpdateTasklistParams:
    tasklist_id: str
    new_title: str

@dataclass
class TasksDeleteTasklistParams:
    tasklist_id: str


@dataclass
class TasksListTasksParams:
    tasklist_id: str
    showCompleted: bool = True
    showDeleted: bool = False
    showHidden: bool = False
    updatedMin: Optional[str] = None
    dueMin: Optional[str] = None
    dueMax: Optional[str] = None
    maxResults: Optional[int] = None

@dataclass
class TasksGetTaskParams:
    tasklist_id: str
    task_id: str

@dataclass
class TasksCreateTaskParams:
    tasklist_id: str
    title: str
    notes: Optional[str] = None
    due: Optional[str] = None  # Could be RFC3339 dateTime or just YYYY-MM-DD

@dataclass
class TasksUpdateTaskParams:
    tasklist_id: str
    task_id: str
    fields_to_update: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TasksDeleteTaskParams:
    tasklist_id: str
    task_id: str

@dataclass
class TasksClearCompletedParams:
    tasklist_id: str

@dataclass
class TasksMoveTaskParams:
    tasklist_id: str
    task_id: str
    parent: Optional[str] = None
    previous: Optional[str] = None
