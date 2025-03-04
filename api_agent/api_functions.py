# api_functions.py
import json
import os
import pickle
import base64
import aiohttp 
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials




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
    CalendarDeleteEventParams,
    CalendarMoveEventParams
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


SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/tasks.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events.readonly"
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
    def __init__(self, credentials):
        self.service = build('calendar', 'v3', credentials=credentials)

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

        elif action.action_type == APIActionType.CALENDAR_MOVE_EVENT:
            params = CalendarMoveEventParams(**(action.parameters or {}))
            return self.move_event(params)

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

        if "date" in start_obj and "date" in end_obj and (start_obj["date"] == end_obj["date"]):
            from datetime import datetime, timedelta
            start_date = datetime.strptime(start_obj["date"], "%Y-%m-%d").date()
            end_date = start_date + timedelta(days=1)
            end_obj["date"] = end_date.isoformat()

        event = {
            'summary': params.summary,
            'description': params.description or "",
            'location': params.location or ""
        }

        if "dateTime" in start_obj:
            start_obj["timeZone"] = params.timeZone
        if "dateTime" in end_obj:
            end_obj["timeZone"] = params.timeZone

        event['start'] = start_obj
        event['end'] = end_obj

        if params.colorId:
            event['colorId'] = params.colorId
        if params.transparency:
            event['transparency'] = params.transparency
        if params.visibility:
            event['visibility'] = params.visibility

        # <--- MODIFICATION: allow using params.calendarId if provided --->
        calendar_id = getattr(params, 'calendarId', None)
        if not calendar_id:
            calendar_id = 'primary'

        created = self.service.events().insert(calendarId=calendar_id, body=event).execute()
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
        cal_id = params.calendarId or 'primary'  # fallback to 'primary' if not set

        event = self.service.events().get(
            calendarId=cal_id,
            eventId=params.event_id
        ).execute()

        for key, val in params.fields_to_update.items():
            event[key] = val

        updated = self.service.events().update(
            calendarId=cal_id,
            eventId=params.event_id,
            body=event
        ).execute()

        return updated

    def delete_event(self, params: CalendarDeleteEventParams) -> Any:
        cal_id = params.calendarId or 'primary'  # fallback to 'primary' if not set

        self.service.events().delete(
            calendarId=cal_id,
            eventId=params.event_id
        ).execute()
        return {"status": "deleted", "event_id": params.event_id}

    def move_event(self, params: CalendarMoveEventParams) -> Any:
        """
        Moves an event from 'sourceCalendarId' to 'destinationCalendarId' using
        the Calendar API's events().move() endpoint.
        """
        return self.service.events().move(
            calendarId=params.sourceCalendarId,
            eventId=params.event_id,
            destination=params.destinationCalendarId
        ).execute()


# ---------------------------------------------------------------------------
#                           GoogleTasksAPIHandler
# ---------------------------------------------------------------------------

class GoogleTasksAPIHandler:
    def __init__(self, credentials):
        self.service = build('tasks', 'v1', credentials=credentials)

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
        """
        Moves a task within the same list OR across different lists,
        using the optional 'destinationTasklist' query parameter.
        """
        return self.service.tasks().move(
            tasklist=p.tasklist_id,
            task=p.task_id,
            parent=p.parent,
            previous=p.previous,
            destinationTasklist=p.destinationTasklist
        ).execute()




