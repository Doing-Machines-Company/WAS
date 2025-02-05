# api_actions_params_gradescope.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GradescopeListCoursesParams:
    """
    Parameters for the GRADESCOPE_LIST_COURSES action.
    Lists all ACTIVE courses visible to the student in a course.
    """
    pass
@dataclass
class GradescopeListAssignmentsParams:
    """
    Parameters for the GRADESCOPE_LIST_ASSIGNMENTS action.
    Lists all assignments visible to the student in a course.
    """

    course_id: str
    include: Optional[List[str]] = None  # ['due_at', 'rubric', 'submission']
