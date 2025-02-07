# gcal_gtasks_api_agent.py

import os
import string
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from api_agent import APIAgent
from api_agent_classes import APIAction, APIActionType, APILinearMemory
from api_llm_handling import LLMMessage, AgentCall
from call_llm import call_llm

from api_functions import GoogleCalendarAPIHandler, GoogleTasksAPIHandler

class GCalGTasksAPIAgent(APIAgent):
    """
    A unified agent that can handle both Google Calendar events and Google Tasks items.
    """
    def __init__(self, task="", fast_mode=False, retry_cap=10, from_user=True, user_timezone="America/New_York"):
        super().__init__(fast_mode=fast_mode, api="google_calendar", retry_cap=retry_cap, from_user=from_user)
        self.task = task
        self.current_datetime = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.user_timezone = user_timezone

        # We'll hold both calendars and tasks lists
        self.all_calendars = []
        self.all_tasklists = []

        if self.from_user:
            # Load the system prompt
            system_prompt_path = os.path.join("api_prompts/gtasks+gcal", "google_calendar_tasks_system.txt")
            self.system_prompt_str = self._load_file(system_prompt_path)

            # Load the user prompt template
            user_prompt_path = os.path.join("api_prompts/gtasks+gcal", "google_calendar_tasks_user.txt")
            self.user_prompt_template = self._load_file(user_prompt_path)
        else:
            # Load the system prompt
            system_prompt_path = os.path.join("api_prompts/gtasks+gcal", "google_calendar_tasks_system_fromapi.txt")
            self.system_prompt_str = self._load_file(system_prompt_path)

            # Load the user prompt template
            user_prompt_path = os.path.join("api_prompts/gtasks+gcal", "google_calendar_tasks_user_fromapi.txt")
            self.user_prompt_template = self._load_file(user_prompt_path)


    def initialize_api_handler(self):
        # Initialize separate handlers for each
        self.gcal_handler = GoogleCalendarAPIHandler()
        self.gtasks_handler = GoogleTasksAPIHandler()

    def _load_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def setup(self):
        # 1) Fetch all calendars
        try:
            list_calendars_action = APIAction(
                action_type=APIActionType.CALENDAR_LIST_CALENDARS,
                reason="Fetch all calendars for unified agent context",
                parameters={}
            )
            cals = self.gcal_handler.perform_action(list_calendars_action)
            self.all_calendars = cals if isinstance(cals, list) else []
        except Exception as e:
            print("Error fetching calendars in GCalGTasksAPIAgent:", e)
            self.all_calendars = []

        # 2) Fetch all task lists
        try:
            list_tasklists_action = APIAction(
                action_type=APIActionType.TASKS_LIST_TASKLISTS,
                reason="Fetch all task lists for unified agent context",
                parameters={}
            )
            tls = self.gtasks_handler.perform_action(list_tasklists_action)
            self.all_tasklists = tls if isinstance(tls, list) else []
        except Exception as e:
            print("Error fetching task lists in GCalGTasksAPIAgent:", e)
            self.all_tasklists = []


    async def call_action(self, provider: str = "anthropic", model: str = "claude-3-5-sonnet-latest") -> AgentCall:
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += f"- Step {i+1} => Called: {mem.call} | Received: {mem.received}\n"

        user_prompt_str = string.Template(self.user_prompt_template).substitute({
            "memory": memory_text.strip(),
            "task": self.task if self.task else "",
            "available_calendars": str(self.all_calendars),
            "available_tasklists": str(self.all_tasklists),
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
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="No valid action or parsing failure",
                parameters=None
            )

        agent_call.parsed_output = chosen_action
        return agent_call

    async def handle_actions(self, action: APIAction):
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

            await self.output_queue.put(('exit_message', "GCal+Tasks Agent has stopped."))
            self.stop()

        else:
            # Single-step
            try:
                result = self._dispatch_action(action)
                success = True
            except Exception as e:
                print("[Unified Agent] Error performing API action:", e)
                success = False

            if not success:
                self.failed_count += 1
                if self.failed_count > self.retry_cap:
                    self.stop()
            else:
                self.failed_count = 0
                if result is None:
                    print("[Unified Agent] Result from _dispatch_action is None (skipping).")

                # Log the action => include parameters in the memory's "call"
                call_str = f"{action.action_type.value} with parameters: {action.parameters}"
                new_memory = APILinearMemory(
                    api_type=self.api,
                    call=call_str,
                    received=str(result) if result else ""
                )
                self.action_mem.append(new_memory)


    def _parse_utc_datetime_or_date(self, dt_str: str) -> datetime:
        """
        Attempt to parse 'dt_str' as an RFC3339 (or ISO) datetime in UTC.
        If there's no time component, interpret it as that date at 00:00 UTC.
        """
        if "T" not in dt_str:
            # e.g. "2025-09-07"
            dt_str = dt_str.strip() + "T00:00:00Z"
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    def _dispatch_action(self, action: APIAction):
        """
        Before sending actions to GoogleCalendarAPIHandler or GoogleTasksAPIHandler:
         - If the event/task is "old" (start/due < now in UTC), skip creation.
         - For tasks, we base the due date on the *local* date, i.e. if it is the previous day local,
           then 'due' is that local day.
         - Insert "(Due local_time_str)" in the title if a time is present.
         - Append "(UTC: ...)" to notes with the original input string.
         - Always append "created by inbound.fyi".
        """
        now_utc = datetime.now(timezone.utc)

        # ---------------------------
        # 1) Calendar events
        # ---------------------------
        if action.action_type in [APIActionType.CALENDAR_CREATE_EVENT, APIActionType.CALENDAR_UPDATE_EVENT]:
            params = action.parameters
            desc = params.get("description", "") or ""

            start_val = params.get("start")
            if start_val:
                event_start_utc = self._parse_utc_datetime_or_date(start_val)
                if event_start_utc < now_utc:
                    print("Event is in the past, skipping creation/update.")
                    return None

            # Append "created by inbound.fyi" to description
            if "created by inbound.fyi" not in desc:
                desc = (desc + "\ncreated by inbound.fyi").strip()
            params["description"] = desc

        # ---------------------------
        # 2) Tasks
        # ---------------------------
        elif action.action_type in [APIActionType.TASKS_CREATE_TASK, APIActionType.TASKS_UPDATE_TASK]:
            params = action.parameters
            notes = params.get("notes", "") or ""
            title = params.get("title", "") or ""
            original_due_str = params.get("due")

            if original_due_str:
                # 1) Parse in UTC to check if it's in the past
                due_utc = self._parse_utc_datetime_or_date(original_due_str)
                if due_utc < now_utc:
                    print("Task due date is in the past, skipping creation/update.")
                    return None

                # 2) Convert UTC -> local time
                #    We'll use the *local date* as the day for the task
                dt_local = due_utc.astimezone(ZoneInfo(self.user_timezone))

                # If there's a time portion originally, show it in the title
                if "T" in original_due_str:
                    # local_time_str = dt_local.strftime("%H:%M %Z")
                    local_time_str = dt_local.strftime("%b %d %H:%M %Z")
                    title = f"{title} (Due {local_time_str})".strip()

                # 3) For the API call, build an RFC3339 date/time using the local date but zeroed time.
                local_date_str = dt_local.strftime("%Y-%m-%d")  # e.g. "2025-09-06"
                final_due = f"{local_date_str}T00:00:00.000Z"
                params["due"] = final_due
                params["title"] = title

                # 4) Append the original UTC date/time to the notes
                notes = notes.rstrip() + f"\n(UTC: {original_due_str})"

            # Append "created by inbound.fyi" to notes
            if "created by inbound.fyi" not in notes:
                notes = (notes + "\ncreated by inbound.fyi").strip()

            params["notes"] = notes

        # ---------------------------
        # Dispatch to API Handler
        # ---------------------------
        ctype = action.action_type
        if ctype in [
            APIActionType.CALENDAR_LIST_CALENDARS,
            APIActionType.CALENDAR_LIST_EVENTS,
            APIActionType.CALENDAR_CREATE_EVENT,
            APIActionType.CALENDAR_UPDATE_EVENT,
            APIActionType.CALENDAR_DELETE_EVENT
        ]:
            result = self.gcal_handler.perform_action(action)
            print("  [Calendar Action] result =", result)
            return result

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
            APIActionType.TASKS_MOVE_TASK
        ]:
            result = self.gtasks_handler.perform_action(action)
            print("  [Tasks Action] result =", result)
            return result
        else:
            print("[Unified Agent] Unrecognized action type:", ctype)
            return None

if __name__ == "__main__":
    # Simple test
    agent = GCalGTasksAPIAgent(
        task="I need to complete homework by March 1, and I have a doctor's appointment on June 1 at 10 AM.",
        user_timezone="America/Los_Angeles"
    )
    asyncio.run(agent.run())
