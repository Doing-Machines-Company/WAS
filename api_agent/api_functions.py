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
# Import your param classes
from api_type_classes.api_actions_params_gmail import (
    GmailListMessagesParams,
    GmailGetMessageParams,
    GmailSendEmailParams,
    GmailListLabelsParams,
    GmailDeleteMessageParams,
    GmailModifyMessageParams
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
    'https://www.googleapis.com/auth/calendar.events.readonly'
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
        Central dispatcher that routes to the correct Gmail method
        based on the action_type.
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

        elif action.action_type == APIActionType.GMAIL_DELETE_MESSAGE:
            params = GmailDeleteMessageParams(**(action.parameters or {}))
            return self.delete_message(params)

        elif action.action_type == APIActionType.GMAIL_MODIFY_MESSAGE:
            params = GmailModifyMessageParams(**(action.parameters or {}))
            return self.modify_message(params)

        else:
            raise ValueError(f"Gmail: Unsupported action type: {action.action_type}")

    def list_messages(self, params: GmailListMessagesParams) -> Any:
        label_ids = [params.labelId] if params.labelId else None
        result = self.service.users().messages().list(
            userId=params.userId,
            labelIds=label_ids
        ).execute()
        return result.get('messages', [])

    def get_message(self, params: GmailGetMessageParams) -> Any:
        """
        Retrieve a message with given ID and optional format.
        """
        response = self.service.users().messages().get(
            userId=params.userId,
            id=params.messageId,
            format=params.format
        ).execute()
        return response

    def send_email(self, params: GmailSendEmailParams) -> Any:
        """
        Example of sending an email with typed parameters.
        """
        message = MIMEText(params.body)
        message['to'] = params.to
        message['from'] = 'your-email@gmail.com'
        message['subject'] = params.subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'raw': raw}
        result = self.service.users().messages().send(
            userId=params.userId,
            body=body
        ).execute()
        return result

    def list_labels(self, params: GmailListLabelsParams) -> Any:
        labels = self.service.users().labels().list(
            userId=params.userId
        ).execute()
        return labels.get('labels', [])

    def delete_message(self, params: GmailDeleteMessageParams) -> Any:
        """
        Deletes the specified message (moves it to Trash, after which it may
        eventually be removed permanently by Gmail).
        """
        self.service.users().messages().delete(
            userId=params.userId,
            id=params.messageId
        ).execute()
        return {"deleted_message_id": params.messageId, "status": "success"}

    def modify_message(self, params: GmailModifyMessageParams) -> Any:
        """
        Apply or remove labels from a message.
        For example, to mark spam or to apply a custom label.
        """
        body = {}
        if params.addLabelIds:
            body['addLabelIds'] = params.addLabelIds
        if params.removeLabelIds:
            body['removeLabelIds'] = params.removeLabelIds

        response = self.service.users().messages().modify(
            userId=params.userId,
            id=params.messageId,
            body=body
        ).execute()
        return response


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
        """
        No parameters, but typed for consistency if we add them later.
        """
        response = self.service.calendarList().list().execute()
        return response.get('items', [])

    def create_event(self, params: CalendarCreateEventParams) -> Any:
        event = {
            'summary': params.summary,
            'location': params.location,
            'description': params.description,
            'start': {
                'dateTime': params.start.isoformat(),
                'timeZone': params.timeZone,
            },
            'end': {
                'dateTime': params.end.isoformat(),
                'timeZone': params.timeZone,
            },
        }
        created = self.service.events().insert(calendarId='primary', body=event).execute()
        return created

    def list_events(self, params: CalendarListEventsParams) -> Any:
        now = (params.timeMin or datetime.utcnow()).isoformat() + 'Z'
        response = self.service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=params.maxResults,
            singleEvents=params.singleEvents,
            orderBy=params.orderBy
        ).execute()
        return response.get('items', [])

    def update_event(self, params: CalendarUpdateEventParams) -> Any:
        event = self.service.events().get(
            calendarId='primary',
            eventId=params.event_id
        ).execute()

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
