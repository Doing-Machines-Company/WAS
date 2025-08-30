from agents.gradescope.gradescopeapi.classes.connection import GSConnection
import datetime
from datetime import timezone


from handler_parameters.api_actions_params_gradescope import (
    GradescopeListAssignmentsParams,
    GradescopeListCoursesParams
)
from typing import List, Tuple, Dict, Any
from api_agent_classes import APIAction, APIActionType, APILinearMemory

class GradescopeAPIHandler:
    def __init__(self, credentials):
        self.connection = None
        self.credentials = credentials
        self.courses = None
    async def create_connection(self) -> GSConnection:
        if not self.credentials:
            raise Exception("Gradescope credentials for user not found.")
        connection = GSConnection()
        await connection.login(self.credentials["email"], self.credentials["password"])
        self.connection = connection
    async def perform_action(self, action: APIAction) -> Any:

        """
        Route based on action.action_type to call the correct method with strongly typed parameters.
        """
        if not self.connection:
            await self.create_connection()

        if action.action_type == APIActionType.GRADESCOPE_LIST_COURSES:
            params = GradescopeListCoursesParams(**(action.parameters or {}))
            return await self.list_courses(params)

        elif action.action_type == APIActionType.GRADESCOPE_LIST_ASSIGNMENTS:
            params = GradescopeListAssignmentsParams(**(action.parameters or {}))
            return await self.list_assignments(params)

        else:
            raise ValueError(f"Gradescope: Unsupported action type: {action.action_type}")
    async def list_courses(self, params: GradescopeListCoursesParams) -> any:
        """
        Lists active courses for a given user.
        """
        account = self.connection.account
        formatted_courses = []
        try:
            courses_dict = await account.get_courses()
            self.courses = courses_dict['student']
            for course_id, course_obj in self.courses.items():
                course_name = course_obj.full_name if hasattr(course_obj, 'full_name') else str(course_obj)
                formatted_courses.append({"id": course_id, "name": course_name})
            return formatted_courses
        except Exception as e:
            return {"error": f"Error retrieving courses from Gradescope: {str(e)}"}

    async def list_assignments(self, params: GradescopeListAssignmentsParams) -> any:
        """
        List assignments for a course with optional includes.
        Only returns assignments with due dates in the future and within the next two weeks.
        Due dates are converted to ISO 8601 (RFC 3339) format.
        """
        account = self.connection.account
        try:
            if not self.courses:
                course_info_dict = await account.get_courses()
                self.courses = course_info_dict['student']
            course_info = self.courses[params.course_id]
            assignments = await account.get_assignments(params.course_id)
            
            # Get current time in UTC
            now = datetime.datetime.now(timezone.utc)
            
            # Calculate date two weeks from now
            two_weeks_later = now + datetime.timedelta(weeks=2)
            
            # Filter assignments to only show those due within the next two weeks
            future_assignments = []
            for assignment in assignments:
                assignment_dict = assignment.__dict__.copy()
                
                # Convert datetime objects to UTC+0 and then to ISO 8601 (RFC 3339) format
                if assignment.due_date:
                    if assignment.due_date.tzinfo is None:
                        assignment.due_date = assignment.due_date.replace(tzinfo=timezone.utc)
                    else:
                        assignment.due_date = assignment.due_date.astimezone(timezone.utc)
                    assignment_dict['due_date'] = assignment.due_date.isoformat()
                if assignment.late_due_date:
                    if assignment.late_due_date.tzinfo is None:
                        assignment.late_due_date = assignment.late_due_date.replace(tzinfo=timezone.utc)
                    else:
                        assignment.late_due_date = assignment.late_due_date.astimezone(timezone.utc)
                    assignment_dict['late_due_date'] = assignment.late_due_date.isoformat()
                if assignment.release_date:
                    if assignment.release_date.tzinfo is None:
                        assignment.release_date = assignment.release_date.replace(tzinfo=timezone.utc)
                    else:
                        assignment.release_date = assignment.release_date.astimezone(timezone.utc)
                    assignment_dict['release_date'] = assignment.release_date.isoformat()
                
                # Add the html_url to the assignment dictionary
                # Format: https://www.gradescope.com/courses/{course_id}/assignments/{assignment_id}
                # but for now, we actually like to link to the course page
                assignment_dict['html_url'] = f"https://www.gradescope.com/courses/{params.course_id}"
                
                # Check if due_date exists and is within the next two weeks
                if assignment.due_date and now < assignment.due_date <= two_weeks_later:
                    future_assignments.append(assignment_dict)
                # If regular due_date is in the past or more than two weeks away, but late_due_date is within the next two weeks
                elif assignment.late_due_date and now < assignment.late_due_date <= two_weeks_later:
                    future_assignments.append(assignment_dict)
            
            # Standardize the return format to match Canvas
            standardized_assignments = []
            for assignment_dict in future_assignments:
                standardized_assignment = {
                    'assignment_id': assignment_dict.get('assignment_id'),
                    'name': assignment_dict.get('name'),
                    'due_at': assignment_dict.get('due_date'),
                    'late_due_at': assignment_dict.get('late_due_date'),
                    'release_at': assignment_dict.get('release_date'),
                    'points_possible': assignment_dict.get('max_grade'),
                    'html_url': assignment_dict.get('html_url')
                }
                standardized_assignments.append(standardized_assignment)
            
            return {
                'course_name': course_info.full_name if hasattr(course_info, 'full_name') else str(course_info),
                'course_id': params.course_id,
                'platform': 'gradescope',
                'assignments': standardized_assignments
            }
        except Exception as e:
            return {"error": f"Error retrieving assignments from Gradescope: {str(e)}"}
    async def close(self):
        if self.connection:
            await self.connection.close()