# api_actions_params_canvas.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CanvasListCoursesParams:
    """
    Parameters for the CANVAS_LIST_COURSES action.
    Lists all ACTIVE courses visible to the student in a course.
    """
    pass
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

@dataclass
class CanvasListPagesParams:
    """
    Parameters for the CANVAS_LIST_PAGES action.
    Lists all the pages in a course.
    """
    
    course_id: int

@dataclass
class CanvasGetPageParams:
    """
    Parameters for the CANVAS_GET_PAGE action
    Returns the contents of a canvas page
    """
    course_id: int
    page_url: str

@dataclass
class CanvasListFilesParams:
    """
    Parameters for the CANVAS_LIST_FILES action
    Lists all the files in a course.
    """
    course_id: int

@dataclass
class CanvasGetFileParams:
    """
    Parameters for the CANVAS_GET_FILE action
    Gets the raw bytes from a canvas file.
    """
    course_id: int
    file_id: int
