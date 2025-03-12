from canvasapi import Canvas
import aiohttp
from handler_parameters.api_actions_params_canvas import (
    CanvasGetAssignmentDetailsParams,
    CanvasGetGradesParams,
    CanvasGetModuleItemsParams,
    CanvasGetSubmissionHistoryParams,
    CanvasListAssignmentsParams,
    CanvasListModulesParams,
    CanvasListPagesParams,
    CanvasGetPageParams,
    CanvasListCoursesParams,
    CanvasListFilesParams,
    CanvasGetFileParams
)
from typing import List, Tuple, Dict, Any
from api_agent_classes import APIAction, APIActionType, APILinearMemory

class CanvasAPIHandler:
    def __init__(self, credentials):
        self.service = self.create_service(credentials)
        self.base_url = credentials["url"].rstrip('/')  # e.g., "https://canvas.example.com"
        self.headers = {"Authorization": f"Bearer {credentials['token']}"}
        self.session = aiohttp.ClientSession(headers=self.headers)
    def create_service(self, credentials) -> Canvas:
        if not credentials:
            raise Exception("Canvas credentials for user not found")
        return Canvas(credentials["url"], credentials["token"])

    async def perform_action(self, action: APIAction) -> Any:
        """
        Route based on action.action_type to call the correct method with strongly typed parameters.
        """
        if action.action_type == APIActionType.CANVAS_LIST_ASSIGNMENTS:
            params = CanvasListAssignmentsParams(**(action.parameters or {}))
            return await self.list_assignments(params)

        elif action.action_type == APIActionType.CANVAS_GET_ASSIGNMENT_DETAILS:
            params = CanvasGetAssignmentDetailsParams(**(action.parameters or {}))
            return await self.get_assignment_details(params)

        elif action.action_type == APIActionType.CANVAS_LIST_MODULES:
            params = CanvasListModulesParams(**(action.parameters or {}))
            return self.list_modules(params)

        elif action.action_type == APIActionType.CANVAS_GET_MODULE_ITEMS:
            params = CanvasGetModuleItemsParams(**(action.parameters or {}))
            return self.get_module_items(params)

        elif action.action_type == APIActionType.CANVAS_GET_GRADES:
            params = CanvasGetGradesParams(**(action.parameters or {}))
            return self.get_grades(params)

        elif action.action_type == APIActionType.CANVAS_GET_SUBMISSION_HISTORY:
            params = CanvasGetSubmissionHistoryParams(**(action.parameters or {}))
            return self.get_submission_history(params)

        elif action.action_type == APIActionType.CANVAS_LIST_COURSES:
            params = CanvasListCoursesParams(**(action.parameters or {}))
            return await self.list_courses(params)

        elif action.action_type == APIActionType.CANVAS_LIST_PAGES:
            params = CanvasListPagesParams(**(action.parameters or {}))
            return self.list_pages(params)

        elif action.action_type == APIActionType.CANVAS_GET_PAGE:
            params = CanvasGetPageParams(**(action.parameters or {}))
            return self.get_page(params)

        elif action.action_type == APIActionType.CANVAS_LIST_FILES:
            params = CanvasListFilesParams(**(action.parameters or {}))
            return self.list_files(params)

        elif action.action_type == APIActionType.CANVAS_GET_FILE:
            params = CanvasGetFileParams(**(action.parameters or {}))
            return self.get_file(params)

        else:
            raise ValueError(f"Canvas: Unsupported action type: {action.action_type}")
    async def list_courses(self, params: CanvasListCoursesParams) -> any:
        """
        Lists active courses for a given user.
        """
        url = f"{self.base_url}/api/v1/courses"
        # The Canvas API supports filtering courses by enrollment state.
        query_params = {"enrollment_state": "active"}
        try:
            async with self.session.get(url, params=query_params) as response:
                response.raise_for_status()
                courses = await response.json()
                # Adjust the output as needed; here we assume each course JSON object
                # has a 'name' or similar attribute for a string representation.
                return [{"id": course['id'], "name": course['name']} for course in courses]
        except Exception as e:
            return {"error": f"Error retrieving courses: {str(e)}"}

    async def list_assignments(self, params: CanvasListAssignmentsParams) -> any:
        """
        Lists assignments for a course with optional includes.
        """
        try:
            # Retrieve course details first.
            course_url = f"{self.base_url}/api/v1/courses/{params.course_id}"
            async with self.session.get(course_url) as course_resp:
                course_resp.raise_for_status()
                course = await course_resp.json()

            # Build query parameters. If 'include' is provided as a list,
            # the Canvas API expects repeated keys such as include[]=submission_types.
            query_params = {}
            if params.include:
                # If params.include is a list, we build a list of tuples.
                query_params = [("include[]", inc) for inc in params.include]
            query_params.append(("per_page", 100))
            assignment_url = f"{self.base_url}/api/v1/courses/{params.course_id}/assignments"
            async with self.session.get(assignment_url, params=query_params) as assign_resp:
                assign_resp.raise_for_status()
                assignments = await assign_resp.json()

            filtered_assignments = []
            for assignment in assignments:
                filtered_assignment = {
                    'course name': course.get("name", ""),
                    'assignment id': assignment.get("id"),
                    'name': assignment.get("name"),
                    'due_at': assignment.get("due_at"),
                    'points_possible': assignment.get("points_possible"),
                    'submission_types': assignment.get("submission_types")
                }
                filtered_assignments.append(filtered_assignment)
            return filtered_assignments
        except Exception as e:
            return {"error": f"Error retrieving assignments: {str(e)}"}

    async def get_assignment_details(self, params: CanvasGetAssignmentDetailsParams) -> any:
        """
        Gets detailed information about a specific assignment.
        """
        try:
            course_url = f"{self.base_url}/api/v1/courses/{params.course_id}"
            assignment_url = f"{self.base_url}/api/v1/courses/{params.course_id}/assignments/{params.assignment_id}"
            async with self.session.get(course_url) as course_resp:
                course_resp.raise_for_status()
                course = await course_resp.json()

            async with self.session.get(assignment_url) as assign_resp:
                assign_resp.raise_for_status()
                assignment = await assign_resp.json()

            detailed_assignment = {
                'course name': course.get("name", ""),
                'id': assignment.get("id"),
                'name': assignment.get("name"),
                'description': assignment.get("description"),
                'due_at': assignment.get("due_at"),
                'points_possible': assignment.get("points_possible"),
                'submission_types': assignment.get("submission_types")
            }
            return detailed_assignment
        except Exception as e:
            return {"error": f"Error retrieving assignment details: {str(e)}"}



    def list_modules(self, params: CanvasListModulesParams) -> any:
        """
        List all modules in a course with optional includes.
        """
        try:
            course = self.service.get_course(params.course_id)
            modules = list(course.get_modules(include=params.include))
            return modules
        except Exception as e:
            return {"error": f"Error retrieving modules: {str(e)}"}

    def get_module_items(self, params: CanvasGetModuleItemsParams) -> any:
        """
        Get items within a specific module.
        """
        try:
            course = self.service.get_course(params.course_id)
            module = course.get_module(params.module_id)
            items = list(module.get_module_items(include=params.include))
            return items
        except Exception as e:
            return {"error": f"Error retrieving module items: {str(e)}"}

    def get_grades(self, params: CanvasGetGradesParams) -> dict:
        """
        Get grades for the current user in a course.
        Returns a dictionary containing assignment grades.
        """
        try:
            course = self.service.get_course(params.course_id)
            assignments = course.get_assignments()
        except Exception as e:
            return {"error": f"Error retrieving course or assignments: {str(e)}"}

        grades_data = []
        for assignment in assignments:
            # Use a try/except for the API call that might fail (e.g., access disabled)
            try:
                submission = assignment.get_submission('self')
            except Exception:
                submission = None

            grade = getattr(submission, 'grade', None) if submission else None
            score = getattr(submission, 'score', None) if submission else None
            points_possible = getattr(assignment, 'points_possible', None)
            assignment_name = getattr(assignment, 'name', 'Unknown')

            grades_data.append({
                'course name': str(course),
                "assignment_name": assignment_name,
                "grade": grade,
                "score": score,
                "points_possible": points_possible
            })

        return {"course_id": params.course_id, "grades": grades_data}

    def get_submission_history(self, params: CanvasGetSubmissionHistoryParams) -> any:
        """
        Get submission history for an assignment.
        """
        try:
            course = self.service.get_course(params.course_id)
            assignment = course.get_assignment(params.assignment_id)
            history = assignment.get_submission(
                self.service.get_current_user().id, include=params.include
            )
            return history
        except Exception as e:
            return {"error": f"Error retrieving submission history: {str(e)}"}


    def list_pages(self, params: CanvasListPagesParams) -> any:
        """
        List all wiki pages in a course.
        """
        try:
            course = self.service.get_course(params.course_id)
            pages = course.get_pages(per_page=100)
            return list(pages)
        except Exception as e:
            return {"error": f"Error retrieving pages: {str(e)}"}
    def get_page(self, params: CanvasGetPageParams) -> any:
        """
        Get a specific page by URL or ID.
        """
        try:
            course = self.service.get_course(params.course_id)
            page = course.get_page(params.page_url)
            return page
        except Exception as e:
            return {"error": f"Error retrieving page: {str(e)}"}

    def list_files(self, params: CanvasListFilesParams) -> any:
        """
        List files in a course.
        """
        try:
            course = self.service.get_course(params.course_id)
            files = list(course.get_files())
            return files
        except Exception as e:
            return {"error": f"Error retrieving files: {str(e)}"}

    def get_file(self, params: CanvasGetFileParams) -> bytes:
        """
        Download a file from Canvas and return its raw bytes.
        Suitable for passing directly to LLMs or other processors.
        """
        try:
            course = self.service.get_course(params.course_id)
            file = course.get_file(params.file_id)
            response = requests.get(file.url)
            if response.status_code != 200:
                raise Exception(f"Failed to download file: {response.status_code}")
            return response.content
        except Exception as e:
            raise Exception(f"Error retrieving file: {str(e)}")