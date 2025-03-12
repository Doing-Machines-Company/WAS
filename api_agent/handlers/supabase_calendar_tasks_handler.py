# supabase_calendar_tasks_handler.py

import os
from typing import Any, List, Dict
import dotenv
from supabase._async.client import AsyncClient as Client, create_client
from api_agent_classes import APIAction, APIActionType

# Import your param classes
from handler_parameters.supabase_calendar_tasks_params import (
    SupabaseListCalendarEventsParams,
    SupabaseCreateCalendarEventParams,
    SupabaseUpdateCalendarEventParams,
    SupabaseDeleteCalendarEventParams,
    SupabaseListTasksParams,
    SupabaseCreateTaskParams,
    SupabaseUpdateTaskParams,
    SupabaseDeleteTaskParams
)
dotenv.load_dotenv()


class SupabaseCalendarTasksHandler:
    """
    Handler that ensures we only read/write rows belonging to a single user_id,
    if user_id is provided.
    """

    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and/or SUPABASE_KEY env vars not set")
        # Client will be initialized asynchronously.
        self.client: Client = None

    async def init_client(self):
        """
        Asynchronously initialize the Supabase client.
        """
        self.client = await create_client(self.url, self.key)

    async def perform_action(self, action: APIAction) -> Any:
        """
        Dispatch to the correct method based on the action.
        """
        atype = action.action_type

        if atype == APIActionType.SUPABASE_LIST_CALENDAR_EVENTS:
            p = SupabaseListCalendarEventsParams(**action.parameters)
            return await self.list_calendar_events(p)
        elif atype == APIActionType.SUPABASE_CREATE_CALENDAR_EVENT:
            p = SupabaseCreateCalendarEventParams(**action.parameters)
            return await self.create_calendar_event(p)
        elif atype == APIActionType.SUPABASE_UPDATE_CALENDAR_EVENT:
            p = SupabaseUpdateCalendarEventParams(**action.parameters)
            return await self.update_calendar_event(p)
        elif atype == APIActionType.SUPABASE_DELETE_CALENDAR_EVENT:
            p = SupabaseDeleteCalendarEventParams(**action.parameters)
            return await self.delete_calendar_event(p)

        elif atype == APIActionType.SUPABASE_LIST_TASKS:
            p = SupabaseListTasksParams(**action.parameters)
            return await self.list_tasks(p)
        elif atype == APIActionType.SUPABASE_CREATE_TASK:
            p = SupabaseCreateTaskParams(**action.parameters)
            return await self.create_task(p)
        elif atype == APIActionType.SUPABASE_UPDATE_TASK:
            p = SupabaseUpdateTaskParams(**action.parameters)
            return await self.update_task(p)
        elif atype == APIActionType.SUPABASE_DELETE_TASK:
            p = SupabaseDeleteTaskParams(**action.parameters)
            return await self.delete_task(p)
        else:
            raise ValueError(f"Unsupported action for SupabaseCalendarTasksHandler: {atype}")

    # ------------------------------------------------------------------
    # Calendar queries
    # ------------------------------------------------------------------

    async def list_calendar_events(self, params: SupabaseListCalendarEventsParams) -> List[Dict[str, Any]]:
        """
        List all future events from the 'calendar' table, filtering by user_id if given.
        """
        user_id = params.user_id

        query = self.client.table("calendar").select("*").gt("end", "now()")
        if user_id:
            query = query.eq("user_id", user_id)

        query = query.order("start", desc=False)
        response = await query.execute()
        return response.data

    async def create_calendar_event(self, params: SupabaseCreateCalendarEventParams) -> Dict[str, Any]:
        """
        Insert a new row in the 'calendar' table.
        """
        row = {
            "user_id": params.user_id,
            "name": params.name,
            "start": params.start,
            "end": params.end,
            "description": params.description,
            "metadata": params.metadata,
        }

        response = await self.client.table("calendar").insert(row).execute()
        inserted = response.data
        if not inserted:
            return {"error": "No row inserted"}
        return inserted[0]

    async def update_calendar_event(self, params: SupabaseUpdateCalendarEventParams) -> Dict[str, Any]:
        """
        Update an existing calendar event by id and user_id.
        """
        query = self.client.table("calendar").update(params.fields_to_update).eq("id", params.event_id)
        if params.user_id:
            query = query.eq("user_id", params.user_id)
        response = await query.execute()
        updated = response.data
        if not updated:
            return {"error": f"No event found with id={params.event_id} for user={params.user_id}"}
        return updated[0]

    async def delete_calendar_event(self, params: SupabaseDeleteCalendarEventParams) -> Dict[str, Any]:
        """
        Delete a calendar event by id and user_id.
        """
        query = self.client.table("calendar").delete().eq("id", params.event_id)
        if params.user_id:
            query = query.eq("user_id", params.user_id)
        response = await query.execute()
        deleted = response.data
        return {
            "status": "deleted",
            "event_id": params.event_id,
            "rows_deleted": len(deleted)
        }

    # ------------------------------------------------------------------
    # Tasks queries
    # ------------------------------------------------------------------

    async def list_tasks(self, params: SupabaseListTasksParams) -> List[Dict[str, Any]]:
        """
        List tasks in the 'tasks' table that are incomplete or future-due, filtering by user_id.
        """
        user_id = params.user_id

        query = self.client.table("tasks").select("*")
        if user_id:
            query = query.eq("user_id", user_id)

        query = query.or_("status.eq.false,due.gt.now()").order("due", desc=False)
        response = await query.execute()
        return response.data

    async def create_task(self, params: SupabaseCreateTaskParams) -> Dict[str, Any]:
        """
        Insert a new row in the 'tasks' table.
        """
        row = {
            "user_id": params.user_id,
            "name": params.name,
            "due": params.due,
            "description": params.description,
            "metadata": params.metadata,
            "send_notification": params.send_notification,
        }
        response = await self.client.table("tasks").insert(row).execute()
        inserted = response.data
        if not inserted:
            return {"error": "No task inserted"}
        return inserted[0]

    async def update_task(self, params: SupabaseUpdateTaskParams) -> Dict[str, Any]:
        """
        Update a task in the 'tasks' table by id and user_id.
        """
        query = self.client.table("tasks").update(params.fields_to_update).eq("id", params.task_id)
        if params.user_id:
            query = query.eq("user_id", params.user_id)
        response = await query.execute()
        updated = response.data
        if not updated:
            return {"error": f"No task found with id={params.task_id} for user={params.user_id}"}
        return updated[0]

    async def delete_task(self, params: SupabaseDeleteTaskParams) -> Dict[str, Any]:
        """
        Delete a task by id and user_id.
        """
        query = self.client.table("tasks").delete().eq("id", params.task_id)
        if params.user_id:
            query = query.eq("user_id", params.user_id)
        response = await query.execute()
        deleted = response.data
        return {
            "status": "deleted",
            "task_id": params.task_id,
            "rows_deleted": len(deleted)
        }
