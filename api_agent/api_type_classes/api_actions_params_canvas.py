# api_actions_params_canvas.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CanvasListAssignmentsParams:
    """
    Parameters for the CANVAS_LIST_ASSIGNMENTS action.
    Lists all assignments visible to the student in a course.
    """

    course_id: str
    include: Optional[List[str]] = None  # ['due_at', 'rubric', 'submission']


@dataclass
class CanvasGetAssignmentDetailsParams:
    """
    Parameters for the CANVAS_GET_ASSIGNMENT_DETAILS action.
    Gets detailed information about a specific assignment.
    """

    course_id: str
    assignment_id: str


@dataclass
class CanvasListModulesParams:
    """
    Parameters for the CANVAS_LIST_MODULES action.
    Lists all modules in a course with their items and prerequisites.
    """

    course_id: str
    include: Optional[List[str]] = None  # ['items', 'content_details', 'prerequisites']


@dataclass
class CanvasGetModuleItemsParams:
    """
    Parameters for the CANVAS_GET_MODULE_ITEMS action.
    Gets detailed information about items within a specific module.
    """

    course_id: str
    module_id: str
    include: Optional[List[str]] = (
        None  # ['content_details', 'completion_requirements']
    )


@dataclass
class CanvasGetGradesParams:
    """
    Parameters for the CANVAS_GET_GRADES action.
    Views current grades and final grades for a course.
    """

    course_id: str
    include: Optional[List[str]] = (
        None  # ['current_grade', 'final_grade', 'assignment_grades']
    )


@dataclass
class CanvasGetSubmissionHistoryParams:
    """
    Parameters for the CANVAS_GET_SUBMISSION_HISTORY action.
    Views the submission history for an assignment including comments and grades.
    """

    course_id: str
    assignment_id: str
    include: Optional[List[str]] = (
        None  # ['submission_comments', 'grade', 'rubric_assessment']
    )
