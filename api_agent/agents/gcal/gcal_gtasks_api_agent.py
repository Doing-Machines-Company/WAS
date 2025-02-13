# gcal_gtasks_api_agent.py

import os
import string
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from api_agent import APIAgent
from api_agent_classes import APIAction, APIActionType
from api_llm_handling import LLMMessage, AgentCall
from call_llm import call_llm

from api_functions import GoogleCalendarAPIHandler, GoogleTasksAPIHandler


class GCalGTasksAPIAgent(APIAgent):
    """
    A unified agent that can handle both Google Calendar events and Google Tasks items,
    fetching fresh data from both APIs each time we call the LLM. No memory is stored.

    This version:
      - fetches ALL future events (in full) and ALL future tasks (in full) each time,
      - avoids microsecond or double 'Z' issues in timeMin,
      - and puts everything into self.future_events / self.future_tasks unfiltered
        except for skipping canceled events and skipping tasks that have a past due date or are completed.
    """

    def __init__(
            self,
            task="",
            fast_mode=False,
            retry_cap=10,
            from_user=True,
            user_timezone="America/New_York",
            use_ampm=True
    ):
        super().__init__(
            fast_mode=fast_mode,
            api="google_calendar",
            retry_cap=retry_cap,
            from_user=from_user
        )
        self.task = task

        # Build a clean RFC3339 "current_datetime" with no microseconds
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        self.current_datetime = now_utc.isoformat().replace("+00:00", "Z")

        # If no explicit user_timezone given, default to America/New_York
        self.user_timezone = user_timezone if user_timezone else "America/New_York"
        self.use_ampm = use_ampm

        # For inbound.fyi references
        self.inbound_fyi_calendar_id = None
        self.inbound_fyi_tasklist_id = None

        # Each LLM invocation we rebuild these
        self.future_events = []
        self.future_tasks = []

        # Load system & user prompts
        if self.from_user:
            # system prompt
            system_prompt_path = os.path.join(
                "api_prompts/gtasks+gcal", "google_calendar_tasks_system.txt"
            )
            self.system_prompt_str = self._load_file(system_prompt_path)

            # user prompt
            user_prompt_path = os.path.join(
                "api_prompts/gtasks+gcal", "google_calendar_tasks_user.txt"
            )
            self.user_prompt_template = self._load_file(user_prompt_path)
        else:
            # system prompt
            system_prompt_path = os.path.join(
                "api_prompts/gtasks+gcal", "google_calendar_tasks_system_fromapi.txt"
            )
            self.system_prompt_str = self._load_file(system_prompt_path)

            # user prompt
            user_prompt_path = os.path.join(
                "api_prompts/gtasks+gcal", "google_calendar_tasks_user_fromapi.txt"
            )
            self.user_prompt_template = self._load_file(user_prompt_path)

    def initialize_api_handler(self):
        # Initialize the separate handlers
        self.gcal_handler = GoogleCalendarAPIHandler()
        self.gtasks_handler = GoogleTasksAPIHandler()

    def _load_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def setup(self):
        """
        Initial (once) setup, if needed. Currently empty because
        we fetch inbound.fyi and tasks/events every time we call the LLM.
        """
        pass

    async def call_action(self, provider: str = "anthropic", model: str = "claude-3-5-sonnet-latest") -> AgentCall:
        """
        Before each LLM call, fetch the latest data:
          - find/create inbound.fyi calendar & tasklist
          - list all calendars + tasks
          - unroll future events and tasks (storing the full dict from the API)
        Then build the prompt with no memory.
        """
        await self._find_or_create_inbound_fyi_calendar()
        await self._find_or_create_inbound_fyi_tasklist()

        # Prepare a timeMin with zero microseconds and "Z" for UTC
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        time_min_iso = now_utc.isoformat().replace("+00:00", "Z")

        # 1) Fetch all calendars
        all_cals = []
        try:
            list_calendars_action = APIAction(
                action_type=APIActionType.CALENDAR_LIST_CALENDARS,
                reason="Fetch updated calendar list",
                parameters={}
            )
            all_cals = self.gcal_handler.perform_action(list_calendars_action)
        except Exception as e:
            print("Error listing calendars:", e)

        # 2) For each calendar, fetch events from timeMin onward
        self.future_events = []
        if isinstance(all_cals, list):
            for cal in all_cals:
                cal_id = cal.get("id")
                if not cal_id:
                    continue
                try:
                    list_events_action = APIAction(
                        action_type=APIActionType.CALENDAR_LIST_EVENTS,
                        reason="Fetch future events for LLM context",
                        parameters={
                            "calendarId": cal_id,
                            "timeMin": time_min_iso,
                            "maxResults": 2500,  # allow more results
                            "singleEvents": True,
                            "orderBy": "startTime",
                            "showDeleted": False
                        }
                    )
                    events_result = self.gcal_handler.perform_action(list_events_action)
                    if isinstance(events_result, list):
                        for evt in events_result:
                            # skip cancelled
                            if evt.get("status") == "cancelled":
                                continue
                            # Store the FULL event object
                            self.future_events.append(evt)
                except Exception as e:
                    print(f"Error fetching events from calendar {cal_id}:", e)

        # 3) Fetch all tasklists
        all_tasklists = []
        try:
            list_tasklists_action = APIAction(
                action_type=APIActionType.TASKS_LIST_TASKLISTS,
                reason="Fetch updated tasklist list",
                parameters={}
            )
            all_tasklists = self.gtasks_handler.perform_action(list_tasklists_action)
        except Exception as e:
            print("Error listing tasklists:", e)

        # 4) For each tasklist, fetch tasks (uncompleted if showCompleted=False, etc.)
        self.future_tasks = []
        if isinstance(all_tasklists, list):
            now_utc_dt = datetime.now(timezone.utc)
            for tlist in all_tasklists:
                tlist_id = tlist.get("id")
                if not tlist_id:
                    continue
                try:
                    list_tasks_action = APIAction(
                        action_type=APIActionType.TASKS_LIST_TASKS,
                        reason="Fetch tasks for LLM context",
                        parameters={
                            "tasklist_id": tlist_id,
                            "showCompleted": True,
                            "showDeleted": False,
                            "showHidden": False,
                            "maxResults": 2500
                        }
                    )
                    tasks_result = self.gtasks_handler.perform_action(list_tasks_action)
                    if isinstance(tasks_result, list):
                        for tsk in tasks_result:
                            # If there's a due date, filter out tasks in the past
                            due_str = tsk.get("due")
                            if due_str:
                                try:
                                    due_dt = self._parse_utc_datetime_or_date(due_str)
                                    if due_dt < now_utc_dt:
                                        # skip stale
                                        continue
                                except:
                                    pass
                            # store the FULL task object
                            self.future_tasks.append(tsk)
                except Exception as e2:
                    print(f"Error listing tasks for tasklist {tlist_id}:", e2)

        # Build user/system prompts (no memory)
        user_prompt_str = string.Template(self.user_prompt_template).substitute({
            "task": self.task,
            "future_events": str(self.future_events),
            "future_tasks": str(self.future_tasks),
        })

        system_prompt_str = string.Template(self.system_prompt_str).substitute({
            "current_datetime": self.current_datetime
        })

        messages = [
            LLMMessage("system", system_prompt_str),
            LLMMessage("user", user_prompt_str),
        ]

        print("[Unified Agent] Calling LLM for next action ...")
        print(user_prompt_str)
        input("LOOK AT USER PROMPT")
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=5000
        )

        print("[Unified Agent] LLM Response:", agent_call.llm_response)
        input("LOOK AT LLM RESPONSE")

        chosen_action = None
        if agent_call.parsed_output:
            for parsed in agent_call.parsed_output:
                if isinstance(parsed, dict) and "action_type" in parsed:
                    try:
                        atype = APIActionType.from_string(parsed["action_type"])
                        chosen_action = APIAction(
                            action_type=atype,
                            reason=parsed.get("reason", ""),
                            parameters=parsed.get("parameters", {})
                        )
                        break
                    except Exception as e:
                        print("[Unified Agent] Error parsing action type:", e)
                        continue

        if not chosen_action:
            # fallback if no parsed action
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="No valid action or parsing failure",
                parameters=None
            )

        agent_call.parsed_output = chosen_action
        return agent_call

    async def handle_actions(self, action: APIAction):
        """
        Perform the action. No memory is stored.
        """
        print(f"[Unified Agent] Handling action => {action.action_type} | Reason: {action.reason}")

        if action.action_type == APIActionType.STOP:
            final_answer = []
            if action.parameters:
                final_answer = action.parameters.get("final_answer", [])

            if final_answer:
                print("[Unified Agent] STOP with final sub-actions => executing them now:")
                for idx, (subaction_str, subparams) in enumerate(final_answer, start=1):
                    try:
                        subaction_type = APIActionType.from_string(subaction_str)
                        sub_action = APIAction(subaction_type, "final_subaction", subparams)
                        self._dispatch_action(sub_action)
                    except Exception as e:
                        print("[Unified Agent] Error executing final sub-action:", e)

            # Then we stop
            await self.output_queue.put(('exit_message', "GCal+Tasks Agent has stopped."))
            self.stop()

        else:
            # Single-step
            try:
                _ = self._dispatch_action(action)
            except Exception as e:
                print("[Unified Agent] Error performing API action:", e)
                self.failed_count += 1
                if self.failed_count > self.retry_cap:
                    self.stop()
                return

            self.failed_count = 0  # reset on success

    # -- Helper to parse UTC times into datetime objects --
    def _parse_utc_datetime_or_date(self, dt_str: str) -> datetime:
        """
        If dt_str is just YYYY-MM-DD, interpret as that day at 00:00Z.
        If dt_str is a full RFC3339 with T..., parse fully.
        """
        if "T" not in dt_str:
            dt_str = dt_str.strip() + "T00:00:00Z"
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    # -- Dispatch the final action to the appropriate API Handler --
    def _dispatch_action(self, action: APIAction):
        now_utc = datetime.now(timezone.utc)

        # For creation: force inbound.fyi usage
        if action.action_type == APIActionType.CALENDAR_CREATE_EVENT:
            params = action.parameters
            # if not set, use user timezone
            if "timeZone" not in params or not params["timeZone"]:
                params["timeZone"] = self.user_timezone
            params["calendarId"] = self.inbound_fyi_calendar_id

        elif action.action_type == APIActionType.TASKS_CREATE_TASK:
            params = action.parameters
            params["tasklist_id"] = self.inbound_fyi_tasklist_id

        # Then do the date/time post-processing as before
        ctype = action.action_type

        # For creating/updating events:
        if ctype in [APIActionType.CALENDAR_CREATE_EVENT, APIActionType.CALENDAR_UPDATE_EVENT]:
            params = action.parameters
            desc = params.get("description", "") or ""
            if "timeZone" not in params or not params["timeZone"]:
                params["timeZone"] = self.user_timezone

            start_val = params.get("start")
            if start_val:
                event_start_utc = self._parse_utc_datetime_or_date(start_val)
                if event_start_utc < now_utc:
                    print("Event is in the past, skipping creation/update.")
                    return None

            # append "created by inbound.fyi"
            if "created by inbound.fyi" not in desc:
                desc = (desc + "\ncreated by inbound.fyi").strip()
            params["description"] = desc

        # For creating/updating tasks:
        if ctype in [APIActionType.TASKS_CREATE_TASK, APIActionType.TASKS_UPDATE_TASK]:
            params = action.parameters
            notes = params.get("notes", "") or ""
            title = params.get("title", "") or ""
            original_due_str = params.get("due")

            if original_due_str:
                due_utc = self._parse_utc_datetime_or_date(original_due_str)
                if due_utc < now_utc:
                    print("Task due date is in the past, skipping creation/update.")
                    return None

                dt_local = due_utc.astimezone(ZoneInfo(self.user_timezone))
                if "T" in original_due_str:
                    # if there's a time portion, add it to the title
                    if self.use_ampm:
                        local_time_str = dt_local.strftime("%b %d %I:%M %p %Z")
                    else:
                        local_time_str = dt_local.strftime("%b %d %H:%M %Z")
                    title = f"{title} (Due {local_time_str})".strip()

                local_date_str = dt_local.strftime("%Y-%m-%d")
                final_due = f"{local_date_str}T00:00:00.000Z"
                params["due"] = final_due
                params["title"] = title
                notes = notes.rstrip() + f"\n(UTC: {original_due_str})"

            if "created by inbound.fyi" not in notes:
                notes = (notes + "\ncreated by inbound.fyi").strip()

            params["notes"] = notes

        # Now delegate to correct API
        if ctype in [
            APIActionType.CALENDAR_LIST_CALENDARS,
            APIActionType.CALENDAR_LIST_EVENTS,
            APIActionType.CALENDAR_CREATE_EVENT,
            APIActionType.CALENDAR_UPDATE_EVENT,
            APIActionType.CALENDAR_DELETE_EVENT,
        ]:
            return self.gcal_handler.perform_action(action)
        elif ctype in [
            APIActionType.TASKS_LIST_TASKLISTS,
            APIActionType.TASKS_GET_TASKLIST,
            APIActionType.TASKS_CREATE_TASKLIST,
            APIActionType.TASKS_UPDATE_TASKLIST,
            APIActionType.TASKS_DELETE_TASKLIST,
            APIActionType.TASKS_LIST_TASKS,
            APIActionType.TASKS_GET_TASK,
            APIActionType.TASKS_CREATE_TASK,
            APIActionType.TASKS_UPDATE_TASK,
            APIActionType.TASKS_DELETE_TASK,
            APIActionType.TASKS_CLEAR_COMPLETED_TASKS,
            APIActionType.TASKS_MOVE_TASK,
        ]:
            return self.gtasks_handler.perform_action(action)
        else:
            print("[Unified Agent] Unrecognized action type:", ctype)
            return None

    async def _find_or_create_inbound_fyi_calendar(self):
        """
        Look for a calendar named "inbound.fyi". If not found, create it.
        Store the calendarId in self.inbound_fyi_calendar_id.
        """
        try:
            result = self.gcal_handler.service.calendarList().list().execute()
            items = result.get("items", [])
            for c in items:
                if c.get("summary") == "inbound.fyi":
                    self.inbound_fyi_calendar_id = c["id"]
                    return
            # Not found => create
            new_cal = self.gcal_handler.service.calendars().insert(body={
                "summary": "inbound.fyi"
            }).execute()
            new_id = new_cal.get("id")
            self.gcal_handler.service.calendarList().insert(body={"id": new_id}).execute()
            self.inbound_fyi_calendar_id = new_id
            print(f"Created dedicated calendar inbound.fyi with ID={new_id}")
        except Exception as e:
            print("Error in _find_or_create_inbound_fyi_calendar:", e)
            self.inbound_fyi_calendar_id = "primary"  # fallback

    async def _find_or_create_inbound_fyi_tasklist(self):
        """
        Look for a task list named "inbound.fyi". If not found, create it.
        Store the ID in self.inbound_fyi_tasklist_id.
        """
        try:
            tlists = self.gtasks_handler.service.tasklists().list().execute()
            items = tlists.get("items", [])
            for tl in items:
                if tl.get("title") == "inbound.fyi":
                    self.inbound_fyi_tasklist_id = tl["id"]
                    return
            # Not found => create
            new_tl = self.gtasks_handler.service.tasklists().insert(body={
                "title": "inbound.fyi"
            }).execute()
            new_id = new_tl.get("id")
            print(f"Created dedicated tasklist inbound.fyi with ID={new_id}")
            self.inbound_fyi_tasklist_id = new_id
        except Exception as e:
            print("Error in _find_or_create_inbound_fyi_tasklist:", e)
            self.inbound_fyi_tasklist_id = None


if __name__ == "__main__":
    # Simple usage test
    agent = GCalGTasksAPIAgent(
        task="I need to write a new blog post by tomorrow at 5 pm, and schedule a meeting on March 8 at 2 pm.",
        user_timezone="America/Los_Angeles"
    )
    asyncio.run(agent.run())
