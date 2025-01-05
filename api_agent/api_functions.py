import os
import pickle
import base64
from email.mime.text import MIMEText
from typing import Optional, Any

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from datetime import datetime, timedelta

from api_agent_classes import APIType, APIActionType

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
    """
    Shared authentication flow for Gmail and Calendar.
    Persists credentials to token.pickle.
    """
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
    """
    Encapsulates all Gmail-specific methods and an action dispatcher.
    """
    def __init__(self):
        self.creds = authenticate()
        self.service = build('gmail', 'v1', credentials=self.creds)

        # Map from APIActionType -> method
        self.action_map = {
            APIActionType.GMAIL_LIST_MESSAGES: self.list_messages,
            APIActionType.GMAIL_GET_MESSAGE: self.get_message,
            APIActionType.GMAIL_SEND_EMAIL: self.send_email,
            APIActionType.GMAIL_LIST_LABELS: self.list_labels
        }

    def perform_action(self, action_type: APIActionType, parameters: Optional[Any] = None) -> Any:
        if action_type not in self.action_map:
            raise ValueError(f"Gmail: Unsupported action type: {action_type}")
        return self.action_map[action_type](parameters)

    def list_messages(self, params: Optional[Any] = None):
        """
        Lists Gmail messages (simplified).
        """
        results = self.service.users().messages().list(userId='me').execute()
        messages = results.get('messages', [])
        return messages

    def get_message(self, params: dict):
        """
        Retrieve a specific message by ID.
        """
        message_id = params.get("message_id")
        if not message_id:
            raise ValueError("Gmail: 'message_id' parameter is required for get_message")
        message = self.service.users().messages().get(userId='me', id=message_id).execute()
        return message

    def send_email(self, params: dict):
        """
        Send an email. 
        params might include: {"to": "...", "subject": "...", "body": "..."}
        """
        to_addr = params.get("to", "recipient@example.com")
        subject = params.get("subject", "Test Email")
        body_text = params.get("body", "This is a test email.")

        message = MIMEText(body_text)
        message['to'] = to_addr
        message['from'] = 'your-email@gmail.com'
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {'raw': raw}

        result = self.service.users().messages().send(userId='me', body=body).execute()
        return result

    def list_labels(self, params: Optional[Any] = None):
        """
        List all labels for the user.
        """
        labels = self.service.users().labels().list(userId='me').execute()
        return labels.get('labels', [])


class GoogleCalendarAPIHandler:
    """
    Encapsulates all Google Calendar-specific methods and an action dispatcher.
    """
    def __init__(self):
        self.creds = authenticate()
        self.service = build('calendar', 'v3', credentials=self.creds)

        self.action_map = {
            APIActionType.CALENDAR_LIST_CALENDARS: self.list_calendars,
            APIActionType.CALENDAR_CREATE_EVENT: self.create_event,
            APIActionType.CALENDAR_LIST_EVENTS: self.list_events,
            APIActionType.CALENDAR_UPDATE_EVENT: self.update_event,
            APIActionType.CALENDAR_DELETE_EVENT: self.delete_event
        }

    def perform_action(self, action_type: APIActionType, parameters: Optional[Any] = None) -> Any:
        if parameters is None:
            raise ValueError(f"Parameters shouldn't be NoneType")
        if action_type not in self.action_map:
            raise ValueError(f"Calendar: Unsupported action type: {action_type}")
        return self.action_map[action_type](parameters)

    def list_calendars(self, params: Optional[Any] = None):
        """
        List user calendars.
        """
        calendars = self.service.calendarList().list().execute()
        return calendars['items']

    def create_event(self, params: dict):
        """
        Create a calendar event. 
        Example params might include 'summary', 'description', 'start', 'end', etc.
        """
        summary = params.get("summary", "Test Event")
        description = params.get("description", "This is a test event.")
        location = params.get("location", "123 Main St.")
        start_time = params.get("start", datetime.now().isoformat())
        end_time = params.get("end", (datetime.now() + timedelta(hours=1)).isoformat())
        timezone = params.get("timeZone", "America/New_York")

        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_time,
                'timeZone': timezone,
            },
        }

        event_result = self.service.events().insert(calendarId='primary', body=event).execute()
        return event_result

    def list_events(self, params: Optional[Any] = None):
        """
        List upcoming events from primary calendar.
        """
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        events_result = self.service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime'
        ).execute()
        return events_result.get('items', [])

    def update_event(self, params: dict):
        """
        Update a specific event. 
        params should include: {"event_id": "...", "fields_to_update": {...}}
        """
        event_id = params.get("event_id")
        if not event_id:
            raise ValueError("Calendar: 'event_id' is required for update_event")

        event = self.service.events().get(calendarId='primary', eventId=event_id).execute()
        fields_to_update = params.get("fields_to_update", {})

        for k, v in fields_to_update.items():
            event[k] = v  # e.g., event['summary'] = 'New Title'

        updated_event = self.service.events().update(
            calendarId='primary', eventId=event_id, body=event
        ).execute()
        return updated_event

    def delete_event(self, params: dict):
        """
        Delete a specific calendar event by its ID.
        """
        event_id = params.get("event_id")
        if not event_id:
            raise ValueError("Calendar: 'event_id' is required for delete_event")

        self.service.events().delete(calendarId='primary', eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}
