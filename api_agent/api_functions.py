# api_functions.py

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

from api_type_classes.api_actions_params_gcal import (
    CalendarListCalendarsParams, CalendarCreateEventParams, CalendarListEventsParams,
    CalendarUpdateEventParams, CalendarDeleteEventParams
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


class GmailAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build('gmail', 'v1', credentials=self.creds)

    def perform_action(self, action: APIAction) -> Any:
        """
        Dispatcher that calls the correct method based on the action_type.
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

        NEEDS TO BE BETTER, but we aren't supporting writing/editing for MVP

        :param params:
        :return:
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
        # Example usage of optional fields
        request_body = {}
        if params.maxResults is not None:
            request_body["maxResults"] = params.maxResults
        if params.minAccessRole is not None:
            request_body["minAccessRole"] = params.minAccessRole
        if params.showHidden is not None:
            request_body["showHidden"] = params.showHidden

        response = self.service.calendarList().list(**request_body).execute()
        return response.get('items', [])

    def create_event(self, params: CalendarCreateEventParams) -> Any:
        # Convert start/end to ISO strings if they are datetimes
        if isinstance(params.start, datetime):
            start_dt = params.start.isoformat()
        else:
            start_dt = str(params.start)
        if not start_dt.endswith('Z') and ('+' not in start_dt[10:] and '-' not in start_dt[10:]):
            start_dt += 'Z'

        if isinstance(params.end, datetime):
            end_dt = params.end.isoformat()
        else:
            end_dt = str(params.end)
        if not end_dt.endswith('Z') and ('+' not in end_dt[10:] and '-' not in end_dt[10:]):
            end_dt += 'Z'

        event = {
            'summary': params.summary,
            'description': params.description,
            'location': params.location,
            'start': {
                'dateTime': start_dt,
                'timeZone': params.timeZone,
            },
            'end': {
                'dateTime': end_dt,
                'timeZone': params.timeZone,
            }
        }
        # Handle optional fields
        if params.colorId:
            event['colorId'] = params.colorId
        if params.transparency:
            event['transparency'] = params.transparency
        if params.visibility:
            event['visibility'] = params.visibility
        # If you had e.g. params.recurrence, set event['recurrence'] = [...]

        created = self.service.events().insert(calendarId='primary', body=event).execute()
        return created

    def list_events(self, params: CalendarListEventsParams) -> Any:
        # Handle timeMin
        if params.timeMin is None:
            time_min_value = datetime.utcnow().isoformat() + 'Z'
        elif isinstance(params.timeMin, datetime):
            time_min_value = params.timeMin.isoformat()
            if not time_min_value.endswith('Z') and ('+' not in time_min_value[10:] and '-' not in time_min_value[10:]):
                time_min_value += 'Z'
        else:
            # It's a string
            time_min_value = params.timeMin
            if not time_min_value.endswith('Z') and ('+' not in time_min_value[10:] and '-' not in time_min_value[10:]):
                time_min_value += 'Z'

        # Handle timeMax
        time_max_value = None
        if params.timeMax:
            if isinstance(params.timeMax, datetime):
                time_max_value = params.timeMax.isoformat()
                if not time_max_value.endswith('Z') and ('+' not in time_max_value[10:] and '-' not in time_max_value[10:]):
                    time_max_value += 'Z'
            else:
                time_max_value = params.timeMax
                if not time_max_value.endswith('Z') and ('+' not in time_max_value[10:] and '-' not in time_max_value[10:]):
                    time_max_value += 'Z'

        request_args = {
            'calendarId': 'primary',
            'timeMin': time_min_value,
            'maxResults': params.maxResults,
            'singleEvents': params.singleEvents,
            'orderBy': params.orderBy
        }
        if time_max_value is not None:
            request_args['timeMax'] = time_max_value
        if params.showDeleted is not None:
            request_args['showDeleted'] = params.showDeleted
        if params.timeZone is not None:
            request_args['timeZone'] = params.timeZone

        response = self.service.events().list(**request_args).execute()
        return response.get('items', [])

    def update_event(self, params: CalendarUpdateEventParams) -> Any:
        event = self.service.events().get(
            calendarId='primary',
            eventId=params.event_id
        ).execute()

        # Merge fields_to_update directly onto the event object
        # For example, if fields_to_update = {"summary": "New Title", "colorId": "1"}
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



class GoogleTasksAPIHandler:
    def __init__(self):
        self.creds = authenticate()
        self.service = build('tasks', 'v1', credentials=self.creds)

    def list_tasklists(self) -> Any:
        """
        Lists all the user's task lists.
        """
        resp = self.service.tasklists().list().execute()
        return resp.get("items", [])

    def get_tasklist(self, tasklist_id: str) -> Any:
        """
        Retrieves a single task list by ID.
        """
        return self.service.tasklists().get(tasklist=tasklist_id).execute()

    def create_tasklist(self, title: str) -> Any:
        """
        Creates a new task list with the given title.
        """
        body = {"title": title}
        return self.service.tasklists().insert(body=body).execute()

    def update_tasklist(self, tasklist_id: str, new_title: str) -> Any:
        """
        Updates the title of a task list.
        """
        body = {"title": new_title}
        return self.service.tasklists().update(tasklist=tasklist_id, body=body).execute()

    def delete_tasklist(self, tasklist_id: str) -> Any:
        """
        Deletes a task list.
        """
        self.service.tasklists().delete(tasklist=tasklist_id).execute()
        return {"status": "deleted", "tasklist_id": tasklist_id}

    # --------------------------------------------------------
    # Task methods
    # --------------------------------------------------------

    def list_tasks(
        self,
        tasklist_id: str,
        show_completed: bool = True,
        show_deleted: bool = False,
        show_hidden: bool = False,
        updated_min: str = None
    ) -> Any:
        """
        Retrieves tasks in a specified task list, optionally filtering by updatedMin
        and whether to show completed/deleted/hidden tasks.
        """
        params = {
            "tasklist": tasklist_id,
            "showCompleted": show_completed,
            "showDeleted": show_deleted,
            "showHidden": show_hidden,
        }
        if updated_min:
            params["updatedMin"] = updated_min

        resp = self.service.tasks().list(**params).execute()
        return resp.get("items", [])

    def get_task(self, tasklist_id: str, task_id: str) -> Any:
        """
        Retrieves a specific task by ID from the specified task list.
        """
        return self.service.tasks().get(
            tasklist=tasklist_id,
            task=task_id
        ).execute()

    def create_task(self, tasklist_id: str, title: str, notes: str = None, due: str = None) -> Any:
        """
        Creates a new task in the specified task list.
        """
        body = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = due  # must be RFC3339 date/time

        return self.service.tasks().insert(tasklist=tasklist_id, body=body).execute()

    def update_task(self, tasklist_id: str, task_id: str, fields_to_update: dict) -> Any:
        """
        Updates an existing task. fields_to_update can contain any valid task fields:
          - title, notes, due, status, etc.
        """
        task = self.service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        for key, val in fields_to_update.items():
            task[key] = val

        return self.service.tasks().update(
            tasklist=tasklist_id,
            task=task_id,
            body=task
        ).execute()

    def delete_task(self, tasklist_id: str, task_id: str) -> Any:
        """
        Deletes a task from the specified task list.
        """
        self.service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
        return {"status": "deleted", "task_id": task_id}

    def clear_completed_tasks(self, tasklist_id: str) -> Any:
        """
        Clears all completed tasks from the specified task list.
        """
        self.service.tasks().clear(tasklist=tasklist_id).execute()
        return {"status": "cleared_completed", "tasklist_id": tasklist_id}

    def move_task(self, tasklist_id: str, task_id: str, parent: str = None, previous: str = None) -> Any:
        """
        Moves the specified task to another position.
        'parent' can be a task ID to make it a subtask,
        'previous' can be a task ID to place it immediately after that sibling.
        """
        params = {
            "tasklist": tasklist_id,
            "task": task_id,
        }
        if parent:
            params["parent"] = parent
        if previous:
            params["previous"] = previous

        return self.service.tasks().move(**params).execute()