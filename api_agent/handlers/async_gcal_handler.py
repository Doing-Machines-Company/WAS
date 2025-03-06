# async_gcal_handler.py
import json
import os
import aiohttp
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Union

from google.oauth2.credentials import Credentials
from api_agent_classes import APIAction, APIActionType

# Calendar param classes
from handler_parameters.api_actions_params_gcal import (
    CalendarListCalendarsParams,
    CalendarCreateEventParams,
    CalendarListEventsParams,
    CalendarUpdateEventParams,
    CalendarDeleteEventParams,
    CalendarMoveEventParams
)


class AsyncGoogleCalendarAPIHandler:
    """
    Asynchronous version of GoogleCalendarAPIHandler that directly uses the Calendar API's endpoint
    instead of the Google client library for better performance with concurrent requests.
    """
    API_BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None


    @property
    def session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def __del__(self):
        if self._session is not None:
            import warnings
            warnings.warn(f"Unclosed session in {self.__class__.__name__}. "
                          f"Please use 'async with' or call the 'close()' method explicitly.")

    async def _make_request(self, method: str, endpoint: str, params: Dict = None, json_data: Dict = None) -> Dict:
        """Make a request to the Google Calendar API"""
        # Refresh token if necessary
        if self.credentials.expired:
            self.credentials.refresh(Request())

        # Get access token
        headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Content-Type": "application/json"
        }

        url = f"{self.API_BASE_URL}{endpoint}"

        async with self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers
        ) as response:
            response_data = await response.json()

            if response.status >= 400:
                error_msg = response_data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"Calendar API error ({response.status}): {error_msg}")

            return response_data

    async def perform_action(self, action: APIAction) -> Any:
        """
        Asynchronous dispatcher for Calendar actions.
        """
        if action.action_type == APIActionType.CALENDAR_LIST_CALENDARS:
            params = CalendarListCalendarsParams(**(action.parameters or {}))
            return await self.list_calendars(params)

        elif action.action_type == APIActionType.CALENDAR_CREATE_EVENT:
            params = CalendarCreateEventParams(**(action.parameters or {}))
            return await self.create_event(params)

        elif action.action_type == APIActionType.CALENDAR_LIST_EVENTS:
            params = CalendarListEventsParams(**(action.parameters or {}))
            return await self.list_events(params)

        elif action.action_type == APIActionType.CALENDAR_UPDATE_EVENT:
            params = CalendarUpdateEventParams(**(action.parameters or {}))
            return await self.update_event(params)

        elif action.action_type == APIActionType.CALENDAR_DELETE_EVENT:
            params = CalendarDeleteEventParams(**(action.parameters or {}))
            return await self.delete_event(params)

        elif action.action_type == APIActionType.CALENDAR_MOVE_EVENT:
            params = CalendarMoveEventParams(**(action.parameters or {}))
            return await self.move_event(params)

        else:
            raise ValueError(f"Calendar: Unsupported action type: {action.action_type}")

    async def list_calendars(self, params: CalendarListCalendarsParams) -> Any:
        """List all calendars for the authenticated user"""
        query_params = {}
        if params.maxResults is not None:
            query_params["maxResults"] = params.maxResults
        if params.minAccessRole is not None:
            query_params["minAccessRole"] = params.minAccessRole
        if params.showHidden is not None:
            query_params["showHidden"] = params.showHidden

        response = await self._make_request("GET", "/users/me/calendarList", params=query_params)
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

    async def create_event(self, params: CalendarCreateEventParams) -> Any:
        """Create a new event in the specified calendar"""
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

        if "dateTime" in start_obj and params.timeZone:
            start_obj["timeZone"] = params.timeZone
        if "dateTime" in end_obj and params.timeZone:
            end_obj["timeZone"] = params.timeZone

        event['start'] = start_obj
        event['end'] = end_obj

        if params.colorId:
            event['colorId'] = params.colorId
        if params.transparency:
            event['transparency'] = params.transparency
        if params.visibility:
            event['visibility'] = params.visibility

        calendar_id = params.calendarId or 'primary'

        return await self._make_request("POST", f"/calendars/{calendar_id}/events", json_data=event)

    async def list_events(self, params: CalendarListEventsParams) -> Any:
        """List events in the specified calendar"""
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

        calendar_id = params.calendarId or "primary"

        query_params = {
            "timeMin": time_min_value,
            "maxResults": params.maxResults,
            "singleEvents": str(params.singleEvents).lower(),
            "orderBy": params.orderBy,
        }

        if time_max_value:
            query_params["timeMax"] = time_max_value
        if params.showDeleted is not None:
            query_params["showDeleted"] = str(params.showDeleted).lower()
        if params.timeZone is not None:
            query_params["timeZone"] = params.timeZone

        response = await self._make_request("GET", f"/calendars/{calendar_id}/events", params=query_params)
        return response.get('items', [])

    async def get_event(self, calendar_id: str, event_id: str) -> Any:
        """Get a specific event by ID"""
        calendar_id = calendar_id or 'primary'
        return await self._make_request("GET", f"/calendars/{calendar_id}/events/{event_id}")

    async def update_event(self, params: CalendarUpdateEventParams) -> Any:
        """Update an existing event"""
        cal_id = params.calendarId or 'primary'

        # First get the current event data
        event = await self.get_event(cal_id, params.event_id)

        # Apply updates
        for key, val in params.fields_to_update.items():
            event[key] = val

        # Send update
        return await self._make_request("PUT", f"/calendars/{cal_id}/events/{params.event_id}", json_data=event)

    async def delete_event(self, params: CalendarDeleteEventParams) -> Any:
        """Delete an event"""
        cal_id = params.calendarId or 'primary'

        await self._make_request("DELETE", f"/calendars/{cal_id}/events/{params.event_id}")
        return {"status": "deleted", "event_id": params.event_id}

    async def move_event(self, params: CalendarMoveEventParams) -> Any:
        """Move an event from one calendar to another"""
        query_params = {
            "destination": params.destinationCalendarId
        }

        return await self._make_request(
            "POST",
            f"/calendars/{params.sourceCalendarId}/events/{params.event_id}/move",
            params=query_params
        )