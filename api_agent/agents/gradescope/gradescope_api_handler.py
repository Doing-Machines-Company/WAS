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
                formatted_courses.append(f"(Course ID: {course_id}, Course Object: {course_obj})")
            return formatted_courses
        except Exception as e:
            return {"error": f"Error retrieving courses from Gradescope: {str(e)}"}

    async def list_assignments(self, params: GradescopeListAssignmentsParams) -> any:
        """
        List assignments for a course with optional includes.
        Only returns assignments with due dates in the future and within the next two weeks.
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
                # Check if due_date exists and is within the next two weeks
                if assignment.due_date and now < assignment.due_date <= two_weeks_later:
                    future_assignments.append(assignment)
                # If regular due_date is in the past or more than two weeks away, but late_due_date is within the next two weeks
                elif assignment.late_due_date and now < assignment.late_due_date <= two_weeks_later:
                    future_assignments.append(assignment)
            
            return f"Course: {course_info}, Future Assignments: {future_assignments}"
        except Exception as e:
            return {"error": f"Error retrieving assignments from Gradescope: {str(e)}"}
    async def close(self):
        await self.connection.close()