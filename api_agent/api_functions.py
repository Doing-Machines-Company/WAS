# api_functions.py
import json
import os
import pickle
import base64
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from datetime import datetime, timedelta

from api_agent_classes import APIAction, APIActionType

# Gmail param classes
from api_type_classes.api_actions_params_gmail import (
    # messages
    GmailListMessagesParams,
    GmailGetMessageParams,
    GmailSendEmailParams,
    GmailListLabelsParams,
    GmailDeleteMessageParams,
    GmailModifyMessageParams,
    # drafts
    GmailListDraftsParams,
    GmailGetDraftParams,
    GmailCreateDraftParams,
    GmailUpdateDraftParams,
    GmailDeleteDraftParams,
    GmailSendDraftParams
)

# Calendar param classes
from api_type_classes.api_actions_params_gcal import (
    CalendarListCalendarsParams,
    CalendarCreateEventParams,
    CalendarListEventsParams,
    CalendarUpdateEventParams,
    CalendarDeleteEventParams
)

# Tasks param classes
from api_type_classes.api_actions_params_gtasks import (
    TasksListTasklistsParams,
    TasksGetTasklistParams,
    TasksCreateTasklistParams,
    TasksUpdateTasklistParams,
    TasksDeleteTasklistParams,
    TasksListTasksParams,
    TasksGetTaskParams,
    TasksCreateTaskParams,
    TasksUpdateTaskParams,
    TasksDeleteTaskParams,
    TasksClearCompletedParams,
    TasksMoveTaskParams
)

#Canvas param classes
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

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.events.readonly',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/tasks.readonly'
]

def authenticate():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

# ---------------------------------------------------------------------------
#                           GmailAPIHandler
# ---------------------------------------------------------------------------

class GmailAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build('gmail', 'v1', credentials=self.creds)

    def perform_action(self, action: APIAction) -> Any:
        """
        Dispatcher for Gmail actions.
        """
        # Messages
        if action.action_type == APIActionType.GMAIL_LIST_MESSAGES:
            return self.list_messages(GmailListMessagesParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_GET_MESSAGE:
            return self.get_message(GmailGetMessageParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_SEND_EMAIL:
            return self.send_email(GmailSendEmailParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_LIST_LABELS:
            return self.list_labels(GmailListLabelsParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_DELETE_MESSAGE:
            return self.delete_message(GmailDeleteMessageParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_MODIFY_MESSAGE:
            return self.modify_message(GmailModifyMessageParams(**action.parameters))

        # Drafts
        elif action.action_type == APIActionType.GMAIL_LIST_DRAFTS:
            return self.list_drafts(GmailListDraftsParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_GET_DRAFT:
            return self.get_draft(GmailGetDraftParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_CREATE_DRAFT:
            return self.create_draft(GmailCreateDraftParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_UPDATE_DRAFT:
            return self.update_draft(GmailUpdateDraftParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_DELETE_DRAFT:
            return self.delete_draft(GmailDeleteDraftParams(**action.parameters))
        elif action.action_type == APIActionType.GMAIL_SEND_DRAFT:
            return self.send_draft(GmailSendDraftParams(**action.parameters))

        else:
            raise ValueError(f"Unsupported Gmail action type: {action.action_type}")

    # --------------------
    # MESSAGES
    # --------------------
    def list_messages(self, params: GmailListMessagesParams) -> Any:
        label_ids = [params.labelId] if params.labelId else None
        resp = self.service.users().messages().list(
            userId=params.userId,
            labelIds=label_ids
        ).execute()
        return resp.get('messages', [])

    def get_message(self, params: GmailGetMessageParams) -> Any:
        resp = self.service.users().messages().get(
            userId=params.userId,
            id=params.messageId,
            format=params.format
        ).execute()
        return resp

    def send_email(self, params: GmailSendEmailParams) -> Any:
        msg = MIMEText(params.body)
        msg['to'] = params.to
        msg['from'] = 'your-email@gmail.com'
        msg['subject'] = params.subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        body = {'raw': raw}
        resp = self.service.users().messages().send(
            userId=params.userId,
            body=body
        ).execute()
        return resp

    def list_labels(self, params: GmailListLabelsParams) -> Any:
        resp = self.service.users().labels().list(
            userId=params.userId
        ).execute()
        return resp.get('labels', [])

    def delete_message(self, params: GmailDeleteMessageParams) -> Any:
        self.service.users().messages().delete(
            userId=params.userId,
            id=params.messageId
        ).execute()
        return {"deleted_message_id": params.messageId, "status": "success"}

    def modify_message(self, params: GmailModifyMessageParams) -> Any:
        body = {}
        if params.addLabelIds:
            body['addLabelIds'] = params.addLabelIds
        if params.removeLabelIds:
            body['removeLabelIds'] = params.removeLabelIds

        resp = self.service.users().messages().modify(
            userId=params.userId,
            id=params.messageId,
            body=body
        ).execute()
        return resp

    # --------------------
    # DRAFTS
    # --------------------
    def list_drafts(self, params: GmailListDraftsParams) -> Any:
        resp = self.service.users().drafts().list(
            userId=params.userId
        ).execute()
        return resp.get('drafts', [])

    def get_draft(self, params: GmailGetDraftParams) -> Any:
        resp = self.service.users().drafts().get(
            userId=params.userId,
            id=params.draftId,
            format=params.format  # Some clients accept the 'format' param
        ).execute()
        return resp

    def create_draft(self, params: GmailCreateDraftParams) -> Any:
        msg = MIMEText(params.body)
        msg['to'] = params.to
        msg['from'] = 'your-email@gmail.com'
        msg['subject'] = params.subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
        request_body = {"message": {"raw": raw}}

        resp = self.service.users().drafts().create(
            userId=params.userId,
            body=request_body
        ).execute()
        return resp

    def update_draft(self, params: GmailUpdateDraftParams) -> Any:
        """
        Example update. Minimal for demonstration.
        """
        # 1) Fetch existing draft
        old_draft = self.service.users().drafts().get(
            userId=params.userId,
            id=params.draftId
        ).execute()

        old_msg = old_draft.get("message", {})
        headers = old_msg.get("payload", {}).get("headers", [])

        # 2) Determine new fields or fallback to old
        new_to = params.new_to or self._extract_header(headers, "to") or "someone@example.com"
        new_subject = params.new_subject or self._extract_header(headers, "subject") or "No Subject"
        new_body = params.new_body or "(empty body)"

        # 3) Build new MIME
        mime_msg = MIMEText(new_body)
        mime_msg['to'] = new_to
        mime_msg['from'] = 'your-email@gmail.com'
        mime_msg['subject'] = new_subject

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode('utf-8')
        request_body = {
            "id": params.draftId,
            "message": {"raw": raw}
        }

        # 4) Update
        updated = self.service.users().drafts().update(
            userId=params.userId,
            id=params.draftId,
            body=request_body
        ).execute()
        return updated

    def delete_draft(self, params: GmailDeleteDraftParams) -> Any:
        self.service.users().drafts().delete(
            userId=params.userId,
            id=params.draftId
        ).execute()
        return {"deleted_draft_id": params.draftId, "status": "success"}

    def send_draft(self, params: GmailSendDraftParams) -> Any:
        resp = self.service.users().drafts().send(
            userId=params.userId,
            body={"id": params.draftId}
        ).execute()
        return resp

    def _extract_header(self, headers, name):
        """
        Helper to find a particular header in a message payload
        """
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

# ---------------------------------------------------------------------------
#                           GoogleCalendarAPIHandler
# ---------------------------------------------------------------------------

class GoogleCalendarAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build('calendar', 'v3', credentials=self.creds)

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
        request_body = {}
        if params.maxResults is not None:
            request_body["maxResults"] = params.maxResults
        if params.minAccessRole is not None:
            request_body["minAccessRole"] = params.minAccessRole
        if params.showHidden is not None:
            request_body["showHidden"] = params.showHidden

        response = self.service.calendarList().list(**request_body).execute()
        return response.get('items', [])

    def _is_all_day_string(self, value: str) -> bool:
        """
        Returns True if 'value' is in YYYY-MM-DD format (no 'T'), meaning an all-day event.
        """
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _parse_date_or_datetime(self, possibly_dt) -> dict:
        """
        Returns a dict suitable for an event's 'start'/'end' field:
         - {"date": "..."} for all-day
         - {"dateTime": "..."} for timed events
        """
        if isinstance(possibly_dt, datetime):
            iso_str = possibly_dt.isoformat()
            # If using naive or UTC, might append 'Z':
            if iso_str.endswith("+00:00"):
                iso_str = iso_str.replace("+00:00", "Z")
            return {"dateTime": iso_str}

        elif isinstance(possibly_dt, str):
            if self._is_all_day_string(possibly_dt):
                # all-day event
                return {"date": possibly_dt}
            else:
                # timed event
                return {"dateTime": possibly_dt}

        else:
            # Fallback = now
            now_iso = datetime.utcnow().isoformat() + "Z"
            return {"dateTime": now_iso}

    def create_event(self, params: CalendarCreateEventParams) -> Any:
        start_obj = self._parse_date_or_datetime(params.start)
        end_obj = self._parse_date_or_datetime(params.end)

        # If user wants all-day and start == end, shift end +1 day
        if "date" in start_obj and "date" in end_obj and (start_obj["date"] == end_obj["date"]):
            from datetime import datetime, timedelta
            start_date = datetime.strptime(start_obj["date"], "%Y-%m-%d").date()
            end_date = start_date + timedelta(days=1)
            end_obj["date"] = end_date.isoformat()

        event = {
            'summary': params.summary,
            'description': params.description or "",  # fallback to empty if None
            'location': params.location or ""
        }

        if "dateTime" in start_obj:
            start_obj["timeZone"] = params.timeZone
        if "dateTime" in end_obj:
            end_obj["timeZone"] = params.timeZone

        event['start'] = start_obj
        event['end'] = end_obj

        # Optional fields
        if params.colorId:
            event['colorId'] = params.colorId
        if params.transparency:
            event['transparency'] = params.transparency
        if params.visibility:
            event['visibility'] = params.visibility

        # For simplicity, always use "primary" calendar
        created = self.service.events().insert(calendarId='primary', body=event).execute()
        return created

    def list_events(self, params: CalendarListEventsParams) -> Any:
        if params.timeMin is None:
            time_min_value = datetime.utcnow().isoformat() + 'Z'
        elif isinstance(params.timeMin, datetime):
            time_min_value = params.timeMin.isoformat()
            if not time_min_value.endswith('Z') and \
               ('+' not in time_min_value[10:] and '-' not in time_min_value[10:]):
                time_min_value += 'Z'
        else:
            time_min_value = params.timeMin
            if not time_min_value.endswith('Z') and \
               ('+' not in time_min_value[10:] and '-' not in time_min_value[10:]):
                time_min_value += 'Z'

        time_max_value = None
        if params.timeMax:
            if isinstance(params.timeMax, datetime):
                time_max_value = params.timeMax.isoformat()
                if not time_max_value.endswith('Z') and \
                   ('+' not in time_max_value[10:] and '-' not in time_max_value[10:]):
                    time_max_value += 'Z'
            else:
                time_max_value = params.timeMax
                if not time_max_value.endswith('Z') and \
                   ('+' not in time_max_value[10:] and '-' not in time_max_value[10:]):
                    time_max_value += 'Z'

        calendar_id = params.calendarId if params.calendarId else "primary"

        request_args = {
            "calendarId": calendar_id,
            "timeMin": time_min_value,
            "maxResults": params.maxResults,
            "singleEvents": params.singleEvents,
            "orderBy": params.orderBy,
        }
        if time_max_value:
            request_args["timeMax"] = time_max_value
        if params.showDeleted is not None:
            request_args["showDeleted"] = params.showDeleted
        if params.timeZone is not None:
            request_args["timeZone"] = params.timeZone

        response = self.service.events().list(**request_args).execute()
        return response.get('items', [])

    def update_event(self, params: CalendarUpdateEventParams) -> Any:
        event = self.service.events().get(calendarId='primary', eventId=params.event_id).execute()

        for key, val in params.fields_to_update.items():
            event[key] = val

        updated = self.service.events().update(
            calendarId='primary',
            eventId=params.event_id,
            body=event
        ).execute()
        return updated

    def delete_event(self, params: CalendarDeleteEventParams) -> Any:
        self.service.events().delete(
            calendarId='primary',
            eventId=params.event_id
        ).execute()
        return {"status": "deleted", "event_id": params.event_id}


# ---------------------------------------------------------------------------
#                           GoogleTasksAPIHandler
# ---------------------------------------------------------------------------

class GoogleTasksAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build('tasks', 'v1', credentials=self.creds)

    def perform_action(self, action: APIAction) -> Any:
        """Dispatcher for Tasks actions, using your param dataclasses."""
        if action.action_type == APIActionType.TASKS_LIST_TASKLISTS:
            p = TasksListTasklistsParams(**(action.parameters or {}))
            return self._list_tasklists(p)
        elif action.action_type == APIActionType.TASKS_GET_TASKLIST:
            p = TasksGetTasklistParams(**(action.parameters or {}))
            return self._get_tasklist(p)
        elif action.action_type == APIActionType.TASKS_CREATE_TASKLIST:
            p = TasksCreateTasklistParams(**(action.parameters or {}))
            return self._create_tasklist(p)
        elif action.action_type == APIActionType.TASKS_UPDATE_TASKLIST:
            p = TasksUpdateTasklistParams(**(action.parameters or {}))
            return self._update_tasklist(p)
        elif action.action_type == APIActionType.TASKS_DELETE_TASKLIST:
            p = TasksDeleteTasklistParams(**(action.parameters or {}))
            return self._delete_tasklist(p)

        elif action.action_type == APIActionType.TASKS_LIST_TASKS:
            p = TasksListTasksParams(**(action.parameters or {}))
            return self._list_tasks(p)
        elif action.action_type == APIActionType.TASKS_GET_TASK:
            p = TasksGetTaskParams(**(action.parameters or {}))
            return self._get_task(p)
        elif action.action_type == APIActionType.TASKS_CREATE_TASK:
            p = TasksCreateTaskParams(**(action.parameters or {}))
            return self._create_task(p)
        elif action.action_type == APIActionType.TASKS_UPDATE_TASK:
            p = TasksUpdateTaskParams(**(action.parameters or {}))
            return self._update_task(p)
        elif action.action_type == APIActionType.TASKS_DELETE_TASK:
            p = TasksDeleteTaskParams(**(action.parameters or {}))
            return self._delete_task(p)
        elif action.action_type == APIActionType.TASKS_CLEAR_COMPLETED_TASKS:
            p = TasksClearCompletedParams(**(action.parameters or {}))
            return self._clear_completed_tasks(p)
        elif action.action_type == APIActionType.TASKS_MOVE_TASK:
            p = TasksMoveTaskParams(**(action.parameters or {}))
            return self._move_task(p)

        else:
            raise ValueError(f"Unsupported Tasks action type: {action.action_type}")

    # --------------------------------------------------------
    # Tasklists
    # --------------------------------------------------------
    def _list_tasklists(self, params: TasksListTasklistsParams) -> Any:
        """Lists all user's task lists."""
        request_args = {}
        if params.maxResults is not None:
            request_args["maxResults"] = params.maxResults
        resp = self.service.tasklists().list(**request_args).execute()
        return resp.get("items", [])

    def _get_tasklist(self, params: TasksGetTasklistParams) -> Any:
        return self.service.tasklists().get(tasklist=params.tasklist_id).execute()

    def _create_tasklist(self, params: TasksCreateTasklistParams) -> Any:
        body = {"title": params.title}
        return self.service.tasklists().insert(body=body).execute()

    def _update_tasklist(self, params: TasksUpdateTasklistParams) -> Any:
        body = {"title": params.new_title}
        return self.service.tasklists().update(tasklist=params.tasklist_id, body=body).execute()

    def _delete_tasklist(self, params: TasksDeleteTasklistParams) -> Any:
        self.service.tasklists().delete(tasklist=params.tasklist_id).execute()
        return {"status": "deleted", "tasklist_id": params.tasklist_id}

    # --------------------------------------------------------
    # Tasks
    # --------------------------------------------------------
    def _list_tasks(self, p: TasksListTasksParams) -> Any:
        request_args = {
            "tasklist": p.tasklist_id,
            "showCompleted": p.showCompleted,
            "showDeleted": p.showDeleted,
            "showHidden": p.showHidden
        }
        if p.updatedMin:
            request_args["updatedMin"] = p.updatedMin
        if p.dueMin:
            request_args["dueMin"] = p.dueMin
        if p.dueMax:
            request_args["dueMax"] = p.dueMax
        if p.maxResults is not None:
            request_args["maxResults"] = p.maxResults

        resp = self.service.tasks().list(**request_args).execute()
        return resp.get("items", [])

    def _get_task(self, p: TasksGetTaskParams) -> Any:
        return self.service.tasks().get(
            tasklist=p.tasklist_id,
            task=p.task_id
        ).execute()

    def _create_task(self, p: TasksCreateTaskParams) -> Any:
        body = {"title": p.title}
        if p.notes:
            body["notes"] = p.notes
        if p.due:
            body["due"] = p.due  # Must be RFC 3339 dateTime or YYYY-MM-DD
        return self.service.tasks().insert(
            tasklist=p.tasklist_id, body=body
        ).execute()

    def _update_task(self, p: TasksUpdateTaskParams) -> Any:
        # 1) fetch existing
        task = self.service.tasks().get(tasklist=p.tasklist_id, task=p.task_id).execute()
        # 2) update fields
        for key, val in p.fields_to_update.items():
            task[key] = val
        # 3) push update
        return self.service.tasks().update(
            tasklist=p.tasklist_id,
            task=p.task_id,
            body=task
        ).execute()

    def _delete_task(self, p: TasksDeleteTaskParams) -> Any:
        self.service.tasks().delete(tasklist=p.tasklist_id, task=p.task_id).execute()
        return {"status": "deleted", "task_id": p.task_id}

    def _clear_completed_tasks(self, p: TasksClearCompletedParams) -> Any:
        self.service.tasks().clear(tasklist=p.tasklist_id).execute()
        return {"status": "cleared_completed", "tasklist_id": p.tasklist_id}

    def _move_task(self, p: TasksMoveTaskParams) -> Any:
        request_args = {
            "tasklist": p.tasklist_id,
            "task": p.task_id,
        }
        if p.parent:
            request_args["parent"] = p.parent
        if p.previous:
            request_args["previous"] = p.previous

        return self.service.tasks().move(**request_args).execute()
    
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