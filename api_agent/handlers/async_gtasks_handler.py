# async_gtasks_handler.py
import json
import os
import aiohttp
import asyncio
from datetime import datetime
from typing import Any, Dict, Optional, Union

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from api_agent_classes import APIAction, APIActionType

# Tasks param classes
from handler_parameters.api_actions_params_gtasks import (
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


class AsyncGoogleTasksAPIHandler:
    """
    Asynchronous version of GoogleTasksAPIHandler that directly uses the Tasks API's endpoint
    instead of the Google client library for better performance with concurrent requests.
    """
    API_BASE_URL = "https://tasks.googleapis.com/tasks/v1"

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
        """Make a request to the Google Tasks API"""
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
            if response.status == 204:  # No content response
                return {"status": "success"}

            response_data = await response.json()

            if response.status >= 400:
                error_msg = response_data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"Tasks API error ({response.status}): {error_msg}")

            return response_data

    async def perform_action(self, action: APIAction) -> Any:
        """
        Asynchronous dispatcher for Tasks actions.
        """
        # Tasklists operations
        if action.action_type == APIActionType.TASKS_LIST_TASKLISTS:
            p = TasksListTasklistsParams(**(action.parameters or {}))
            return await self.list_tasklists(p)
        elif action.action_type == APIActionType.TASKS_GET_TASKLIST:
            p = TasksGetTasklistParams(**(action.parameters or {}))
            return await self.get_tasklist(p)
        elif action.action_type == APIActionType.TASKS_CREATE_TASKLIST:
            p = TasksCreateTasklistParams(**(action.parameters or {}))
            return await self.create_tasklist(p)
        elif action.action_type == APIActionType.TASKS_UPDATE_TASKLIST:
            p = TasksUpdateTasklistParams(**(action.parameters or {}))
            return await self.update_tasklist(p)
        elif action.action_type == APIActionType.TASKS_DELETE_TASKLIST:
            p = TasksDeleteTasklistParams(**(action.parameters or {}))
            return await self.delete_tasklist(p)

        # Tasks operations
        elif action.action_type == APIActionType.TASKS_LIST_TASKS:
            p = TasksListTasksParams(**(action.parameters or {}))
            return await self.list_tasks(p)
        elif action.action_type == APIActionType.TASKS_GET_TASK:
            p = TasksGetTaskParams(**(action.parameters or {}))
            return await self.get_task(p)
        elif action.action_type == APIActionType.TASKS_CREATE_TASK:
            p = TasksCreateTaskParams(**(action.parameters or {}))
            return await self.create_task(p)
        elif action.action_type == APIActionType.TASKS_UPDATE_TASK:
            p = TasksUpdateTaskParams(**(action.parameters or {}))
            return await self.update_task(p)
        elif action.action_type == APIActionType.TASKS_DELETE_TASK:
            p = TasksDeleteTaskParams(**(action.parameters or {}))
            return await self.delete_task(p)
        elif action.action_type == APIActionType.TASKS_CLEAR_COMPLETED_TASKS:
            p = TasksClearCompletedParams(**(action.parameters or {}))
            return await self.clear_completed_tasks(p)
        elif action.action_type == APIActionType.TASKS_MOVE_TASK:
            p = TasksMoveTaskParams(**(action.parameters or {}))
            return await self.move_task(p)
        else:
            raise ValueError(f"Unsupported Tasks action type: {action.action_type}")

    # --------------------------------------------------------
    # Tasklists methods
    # --------------------------------------------------------
    async def list_tasklists(self, params: TasksListTasklistsParams) -> Any:
        """Lists all user's task lists."""
        query_params = {}
        if params.maxResults is not None:
            query_params["maxResults"] = params.maxResults

        response = await self._make_request("GET", "/users/@me/lists", params=query_params)
        return response.get("items", [])

    async def get_tasklist(self, params: TasksGetTasklistParams) -> Any:
        """Get a specific tasklist by ID."""
        return await self._make_request("GET", f"/users/@me/lists/{params.tasklist_id}")

    async def create_tasklist(self, params: TasksCreateTasklistParams) -> Any:
        """Create a new tasklist."""
        body = {"title": params.title}
        return await self._make_request("POST", "/users/@me/lists", json_data=body)

    async def update_tasklist(self, params: TasksUpdateTasklistParams) -> Any:
        """Update an existing tasklist title."""
        # First get the current tasklist to preserve etag and other fields
        current_tasklist = await self._make_request("GET", f"/users/@me/lists/{params.tasklist_id}")

        # Update only the title while preserving other fields
        current_tasklist["title"] = params.new_title

        # Send the updated tasklist with all original fields
        return await self._make_request("PUT", f"/users/@me/lists/{params.tasklist_id}", json_data=current_tasklist)

    async def delete_tasklist(self, params: TasksDeleteTasklistParams) -> Any:
        """Delete a tasklist."""
        await self._make_request("DELETE", f"/users/@me/lists/{params.tasklist_id}")
        return {"status": "deleted", "tasklist_id": params.tasklist_id}

    # --------------------------------------------------------
    # Tasks methods
    # --------------------------------------------------------
    async def list_tasks(self, p: TasksListTasksParams) -> Any:
        """List tasks from a specific tasklist."""
        query_params = {
            "showCompleted": str(p.showCompleted).lower(),
            "showDeleted": str(p.showDeleted).lower(),
            "showHidden": str(p.showHidden).lower()
        }

        if p.updatedMin:
            query_params["updatedMin"] = p.updatedMin
        if p.dueMin:
            query_params["dueMin"] = p.dueMin
        if p.dueMax:
            query_params["dueMax"] = p.dueMax
        if p.maxResults is not None:
            query_params["maxResults"] = p.maxResults

        response = await self._make_request(
            "GET",
            f"/lists/{p.tasklist_id}/tasks",
            params=query_params
        )
        return response.get("items", [])

    async def get_task(self, p: TasksGetTaskParams) -> Any:
        """Get a specific task by ID."""
        return await self._make_request("GET", f"/lists/{p.tasklist_id}/tasks/{p.task_id}")

    async def create_task(self, p: TasksCreateTaskParams) -> Any:
        """Create a new task in a tasklist."""
        body = {"title": p.title}
        if p.notes:
            body["notes"] = p.notes
        if p.due:
            body["due"] = p.due

        return await self._make_request(
            "POST",
            f"/lists/{p.tasklist_id}/tasks",
            json_data=body
        )

    async def update_task(self, p: TasksUpdateTaskParams) -> Any:
        """Update an existing task."""
        # 1) fetch existing task
        task = await self._make_request("GET", f"/lists/{p.tasklist_id}/tasks/{p.task_id}")

        # 2) update fields
        for key, val in p.fields_to_update.items():
            task[key] = val

        # 3) push update
        return await self._make_request(
            "PUT",
            f"/lists/{p.tasklist_id}/tasks/{p.task_id}",
            json_data=task
        )

    async def delete_task(self, p: TasksDeleteTaskParams) -> Any:
        """Delete a task."""
        await self._make_request("DELETE", f"/lists/{p.tasklist_id}/tasks/{p.task_id}")
        return {"status": "deleted", "task_id": p.task_id}

    async def clear_completed_tasks(self, p: TasksClearCompletedParams) -> Any:
        """Clear all completed tasks from a tasklist."""
        await self._make_request("POST", f"/lists/{p.tasklist_id}/clear")
        return {"status": "cleared_completed", "tasklist_id": p.tasklist_id}

    async def move_task(self, p: TasksMoveTaskParams) -> Any:
        """
        Move a task within the same list or to a different list.
        """
        query_params = {}
        if p.parent:
            query_params["parent"] = p.parent
        if p.previous:
            query_params["previous"] = p.previous

        endpoint = f"/lists/{p.tasklist_id}/tasks/{p.task_id}/move"

        # If moving to a different tasklist
        if p.destinationTasklist:
            query_params["destination"] = p.destinationTasklist

        return await self._make_request("POST", endpoint, params=query_params)