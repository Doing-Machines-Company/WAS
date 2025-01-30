# api_functions.py
import base64
import json
import os
import pickle
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any
import requests
from api_agent_classes import APIAction, APIActionType
from api_type_classes.api_actions_params_canvas import (
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
from api_type_classes.api_actions_params_gcal import (
    CalendarCreateEventParams,
    CalendarDeleteEventParams,
    CalendarListCalendarsParams,
    CalendarListEventsParams,
    CalendarUpdateEventParams,
)
from api_type_classes.api_actions_params_gmail import (
    GmailGetMessageParams,
    GmailListLabelsParams,
    GmailListMessagesParams,
    GmailSendEmailParams,
)
from canvasapi import Canvas
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]


def authenticate():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return creds


class GmailAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build("gmail", "v1", credentials=self.creds)

    def perform_action(self, action: APIAction) -> Any:
        """
        Route based on action.action_type to call the correct method with strongly typed parameters.
        """
        if action.action_type == APIActionType.GMAIL_LIST_MESSAGES:
            params = GmailListMessagesParams(**(action.parameters or {}))
            return self.list_messages(params)

        elif action.action_type == APIActionType.GMAIL_GET_MESSAGE:
            params = GmailGetMessageParams(**(action.parameters or {}))
            return self.get_message(params)

        elif action.action_type == APIActionType.GMAIL_SEND_EMAIL:
            params = GmailSendEmailParams(**(action.parameters or {}))
            return self.send_email(params)

        elif action.action_type == APIActionType.GMAIL_LIST_LABELS:
            params = GmailListLabelsParams(**(action.parameters or {}))
            return self.list_labels(params)

        else:
            raise ValueError(f"Gmail: Unsupported action type: {action.action_type}")

    def list_messages(self, params: GmailListMessagesParams) -> Any:
        """
        Example method using typed parameters.
        """
        label_ids = [params.labelId] if params.labelId else None
        result = (
            self.service.users()
            .messages()
            .list(userId=params.userId, labelIds=label_ids)
            .execute()
        )
        return result.get("messages", [])

    def get_message(self, params: GmailGetMessageParams) -> Any:
        """
        Retrieve a message with given ID and optional format.
        """
        response = (
            self.service.users()
            .messages()
            .get(userId=params.userId, id=params.messageId, format=params.format)
            .execute()
        )
        return response

    def send_email(self, params: GmailSendEmailParams) -> Any:
        """
        Example of sending an email with typed parameters.
        """
        message = MIMEText(params.body)
        message["to"] = params.to
        message["from"] = "your-email@gmail.com"
        message["subject"] = params.subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body = {"raw": raw}
        result = (
            self.service.users()
            .messages()
            .send(userId=params.userId, body=body)
            .execute()
        )
        return result

    def list_labels(self, params: GmailListLabelsParams) -> Any:
        """
        List all labels for a user.
        """
        labels = self.service.users().labels().list(userId=params.userId).execute()
        return labels.get("labels", [])


class GoogleCalendarAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build("calendar", "v3", credentials=self.creds)

    def perform_action(self, action: APIAction) -> Any:
        if action.action_type == APIActionType.CALENDAR_LIST_CALENDARS:
            params = CalendarListCalendarsParams(**(action.parameters or {}))
            return self.list_calendars(params)

        elif action.action_type == APIActionType.CALENDAR_CREATE_EVENT:
            params = CalendarCreateEventParams(**(action.parameters or {}))
            return self.create_event(params)

        elif action.action_type == APIActionType.CALENDAR_LIST_EVENTS:
            params = CalendarListEventsParams(**(action.parameters or {}))
            return self.list_events(params)

        elif action.action_type == APIActionType.CALENDAR_UPDATE_EVENT:
            params = CalendarUpdateEventParams(**(action.parameters or {}))
            return self.update_event(params)

        elif action.action_type == APIActionType.CALENDAR_DELETE_EVENT:
            params = CalendarDeleteEventParams(**(action.parameters or {}))
            return self.delete_event(params)

        else:
            raise ValueError(f"Calendar: Unsupported action type: {action.action_type}")

    def list_calendars(self, params: CalendarListCalendarsParams) -> Any:
        """
        No parameters, but typed for consistency if we add them later.
        """
        response = self.service.calendarList().list().execute()
        return response.get("items", [])

    def create_event(self, params: CalendarCreateEventParams) -> Any:
        event = {
            "summary": params.summary,
            "location": params.location,
            "description": params.description,
            "start": {
                "dateTime": params.start.isoformat(),
                "timeZone": params.timeZone,
            },
            "end": {
                "dateTime": params.end.isoformat(),
                "timeZone": params.timeZone,
            },
        }
        created = (
            self.service.events().insert(calendarId="primary", body=event).execute()
        )
        return created

    def list_events(self, params: CalendarListEventsParams) -> Any:
        now = (params.timeMin or datetime.utcnow()).isoformat() + "Z"
        response = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=params.maxResults,
                singleEvents=params.singleEvents,
                orderBy=params.orderBy,
            )
            .execute()
        )
        return response.get("items", [])

    def update_event(self, params: CalendarUpdateEventParams) -> Any:
        event = (
            self.service.events()
            .get(calendarId="primary", eventId=params.event_id)
            .execute()
        )

        for key, val in params.fields_to_update.items():
            event[key] = val

        updated = (
            self.service.events()
            .update(calendarId="primary", eventId=params.event_id, body=event)
            .execute()
        )
        return updated

    def delete_event(self, params: CalendarDeleteEventParams) -> Any:
        self.service.events().delete(
            calendarId="primary", eventId=params.event_id
        ).execute()
        return {"status": "deleted", "event_id": params.event_id}


class CanvasAPIHandler:
    def __init__(self):
        self.service = self.create_service()

    def create_service(self) -> Canvas:
        credentials = None
        if os.path.exists("canvas.json"):
            with open("canvas.json", "r") as credentials_file:
                # `credentials` is a dictionary with two keys: `url` and `token`
                credentials = json.load(credentials_file)

        if not credentials:
            raise FileNotFoundError("Unable to find Canvas credentials file.")

        return Canvas(credentials["url"], credentials["token"])

    def perform_action(self, action: APIAction) -> Any:
        """
        Route based on action.action_type to call the correct method with strongly typed parameters.
        """
        if action.action_type == APIActionType.CANVAS_LIST_ASSIGNMENTS:
            params = CanvasListAssignmentsParams(**(action.parameters or {}))
            return self.list_assignments(params)

        elif action.action_type == APIActionType.CANVAS_GET_ASSIGNMENT_DETAILS:
            params = CanvasGetAssignmentDetailsParams(**(action.parameters or {}))
            return self.get_assignment_details(params)

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
            return self.list_courses(params)

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
    def list_courses(self, params: CanvasListCoursesParams) -> Any:
        """
        Lists active courses for a given user

        """
        return [str(course) for course in self.service.get_courses(enrollment_state='active')]

    def list_assignments(self, params: CanvasListAssignmentsParams) -> Any:
        """
        List assignments for a course with optional includes.
        """
        course = self.service.get_course(params.course_id)
        assignments = course.get_assignments(include=params.include)
        filtered_assignments = []
        for assignment in assignments:
            filtered_assignment = {
                'id': assignment.id,
                'name': assignment.name,
                'due_at': assignment.due_at,
                'points_possible': assignment.points_possible,
                'submission_types': assignment.submission_types
            }
            filtered_assignments.append(filtered_assignment)
        return filtered_assignments

    def get_assignment_details(self, params: CanvasGetAssignmentDetailsParams) -> Any:
        """
        Get detailed information about a specific assignment.
        """
        course = self.service.get_course(params.course_id)
        assignment = course.get_assignment(params.assignment_id)
        detailed_assignment = {
            'id': assignment.id,
            'name': assignment.name,
            'description': assignment.description,
            'due_at': assignment.due_at,
            'points_possible': assignment.points_possible,
            'submission_types': assignment.submission_types
        }
        return detailed_assignment



    def list_modules(self, params: CanvasListModulesParams) -> Any:
        """
        List all modules in a course with optional includes.
        """
        course = self.service.get_course(params.course_id)
        return list(course.get_modules(include=params.include))

    def get_module_items(self, params: CanvasGetModuleItemsParams) -> Any:
        """
        Get items within a specific module.
        """
        course = self.service.get_course(params.course_id)
        module = course.get_module(params.module_id)
        return list(module.get_module_items(include=params.include))

    def get_grades(self, params: CanvasGetGradesParams) -> Any:
        """
        Get grades for the current user in a course.
        """
        course = self.service.get_course(params.course_id)

        # Fetch assignments and grades
        assignments = course.get_assignments()
        for assignment in assignments:
            # Fetch the submission for the authenticated user
            submission = assignment.get_submission('self')
            grade = submission.grade
            score = submission.score
            points_possible = assignment.points_possible
            print(f"Assignment: {assignment.name}")
            print(f"  Grade: {grade}")
            print(f"  Score: {score}")
            print(f"  Points Possible: {points_possible}")
            print("-" * 40)
    def get_submission_history(self, params: CanvasGetSubmissionHistoryParams) -> Any:
        """
        Get submission history for an assignment.
        """
        course = self.service.get_course(params.course_id)
        assignment = course.get_assignment(params.assignment_id)
        return assignment.get_submission(
            self.service.get_current_user().id, include=params.include
        )

    def list_pages(self, params: CanvasListPagesParams) -> Any:
        """
        List all wiki pages in a course.
        
        Args:
            params: CanvasListPagesParams containing course_id and optional search parameters
            
        Returns:
            list: All pages in the course
        """
        course = self.service.get_course(params.course_id)
        all_pages = []
        try:
            pages = course.get_pages(per_page=100)
        except Exception as e:
            input(e)
        for page in pages:
            print(page)
        input()
        # while True:
        #     try:
        #         page = next(pages)
        #         all_pages.append(page)
        #     except StopIteration:
        #         break
        
        return all_pages
    def get_page(self, params: CanvasGetPageParams) -> Any:
        """
        Get a specific page by URL or ID.
        
        Args:
            params: CanvasGetPageParams containing course_id and page_url/page_id
            
        Returns:
            Page: The requested page object
        """
        course = self.service.get_course(params.course_id)
        return course.get_page(params.page_url)

    def list_files(self, params: CanvasListFilesParams) -> Any:
        """
        List files in a course.
        
        Args:
            params: CanvasListFilesParams containing course_id and optional search parameters
            
        Returns:
            list: Files in the course matching search criteria
        """
        course = self.service.get_course(params.course_id)
        return list(course.get_files())
    
    def get_file(self, params: CanvasGetFileParams) -> bytes:
        """
        Download a file from Canvas and return its raw bytes.
        Suitable for passing directly to LLMs or other processors.
        
        Args:
            params: CanvasGetFileParams containing course_id and file_id
            
        Returns:
            bytes: Raw file content
            
        Raises:
            Exception: If file download fails
        """
        course = self.service.get_course(params.course_id)
        file = course.get_file(params.file_id)
        
        response = requests.get(file.url)
        if response.status_code != 200:
            raise Exception(f"Failed to download file: {response.status_code}")
        
        return response.content