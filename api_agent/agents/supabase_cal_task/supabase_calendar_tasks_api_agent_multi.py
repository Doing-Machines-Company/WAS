import os
import asyncio
import string
from datetime import datetime, timezone
from typing import Any

from api_agent import APIAgent
from api_agent_classes import APIAction, APIActionType
from api_llm_handling import LLMMessage, AgentCall
from call_llm import call_llm

from handlers.supabase_calendar_tasks_handler import SupabaseCalendarTasksHandler


class SupabaseCalendarTasksAPIAgentMulti(APIAgent):
    """
    A Supabase-based Calendar+Tasks agent that can output multiple actions
    in a single LLM response. If the LLM says "STOP", that is the only action.

    IMPORTANT:
      - We never show the user_id in the enumerations or in prompts.
      - Internally, we always filter queries by the self.user_id so that
        the agent can only see/manipulate its own rows.
    """

    def __init__(
        self,
        task="",
        fast_mode=False,
        retry_cap=10,
        from_user=True,
        user_id=None
    ):
        super().__init__(
            fast_mode=fast_mode,
            api="supabase_calendar_tasks",
            retry_cap=retry_cap,
            from_user=from_user
        )
        self.task = task
        # The user's Supabase UUID. We do not show this in the prompt,
        # but we use it for all queries so we only see their rows.
        self.user_id = user_id

        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        self.current_datetime = now_utc.isoformat().replace("+00:00", "Z")

        # Mappings from enumerated "event_x" -> actual DB ID
        self.event_id_map = {}
        # Mappings from enumerated "task_x" -> actual DB ID
        self.task_id_map = {}

        # System + user prompts
        system_prompt_path = os.path.join(
            "api_prompts/supabase_calendar_tasks",
            "supabase_calendar_tasks_system_multi.txt"
        )
        user_prompt_path = os.path.join(
            "api_prompts/supabase_calendar_tasks",
            "supabase_calendar_tasks_user_multi.txt"
        )

        self.system_prompt_str = self._load_file(system_prompt_path)
        self.user_prompt_template = self._load_file(user_prompt_path)

        # Handler for Supabase queries
        self.supabase_handler = SupabaseCalendarTasksHandler()

    def _load_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def setup(self):
        """Any once-only setup if needed. Currently unused."""
        await self.supabase_handler.init_client()

    def initialize_api_handler(self):
        """Initialize the appropriate API handler based on self.api."""
        pass

    async def call_action(self, provider: str = "anthropic", model: str = "claude-3-5-sonnet-latest") -> AgentCall:
        """
        1) Fetch the user's future events + tasks from Supabase
        2) Enumerate them
        3) Prompt the LLM
        4) Parse an array of actions (or possibly STOP).
        """
        # 1) fetch with user_id filter
        list_cal_params = {"user_id": self.user_id}
        list_task_params = {"user_id": self.user_id}

        future_events, future_tasks = await asyncio.gather(
            self.supabase_handler.perform_action(
                APIAction(APIActionType.SUPABASE_LIST_CALENDAR_EVENTS,
                          "list user calendar events",
                          list_cal_params)
            ),
            self.supabase_handler.perform_action(
                APIAction(APIActionType.SUPABASE_LIST_TASKS,
                          "list user tasks",
                          list_task_params)
            )
        )

        # 2) enumerate them without any mention of user_id
        enumerated_events_str = self._format_enumerated_events(future_events)
        enumerated_tasks_str = self._format_enumerated_tasks(future_tasks)

        # 3) build user prompt
        user_prompt_str = string.Template(self.user_prompt_template).substitute({
            "task": self.task,
            "future_events": enumerated_events_str,
            "future_tasks": enumerated_tasks_str,
        })
        system_prompt_str = string.Template(self.system_prompt_str).substitute({
            "current_datetime": self.current_datetime
        })

        messages = [
            LLMMessage("system", system_prompt_str),
            LLMMessage("user", user_prompt_str),
        ]

        # call LLM
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=3000
        )
        print("[Supabase Agent Multi] LLM response:", agent_call.llm_response)

        # 4) parse the response => array of actions
        parsed_actions = []

        for llm_out in agent_call.parsed_output:
            if isinstance(llm_out, list):
                # The LLM might provide multiple actions
                for item in llm_out:
                    if isinstance(item, dict) and "action_type" in item:
                        try:
                            atype = APIActionType.from_string(item["action_type"])
                            new_action = APIAction(
                                action_type=atype,
                                reason=item.get("reason", ""),
                                parameters=item.get("parameters", {})
                            )
                            parsed_actions.append(new_action)
                        except Exception as e:
                            print("Ignoring unrecognized action:", e)

            elif isinstance(llm_out, dict):
                # Possibly a single STOP
                if "action_type" in llm_out:
                    try:
                        atype = APIActionType.from_string(llm_out["action_type"])
                        new_action = APIAction(
                            action_type=atype,
                            reason=llm_out.get("reason", ""),
                            parameters=llm_out.get("parameters", {})
                        )
                        parsed_actions.append(new_action)
                    except Exception as e:
                        print("Unrecognized single dict action:", e)

            else:
                print("No recognized JSON. Defaulting to STOP.")
                parsed_actions = [APIAction(APIActionType.STOP, "fallback no-action")]

        agent_call.parsed_output = parsed_actions
        return agent_call

    async def handle_actions(self, actions):
        """
        Only stop if STOP is present AND all the other actions succeed.
        If any action fails, we do NOT stop, and we re-enter the loop.
        """
        # Check if STOP is present
        stop_action_present = any(a.action_type == APIActionType.STOP for a in actions)

        # Separate out dispatchable actions (everything except STOP)
        dispatchable_actions = [a for a in actions if a.action_type != APIActionType.STOP]

        # Dispatch all non-STOP actions in parallel
        tasks = [self._dispatch_action(a) for a in dispatchable_actions]

        # We'll consider everything successful only if:
        #  - No exceptions were raised
        #  - Each result passes our custom 'success' check for that action type
        all_succeeded = True
        results = []

        try:
            results = await asyncio.gather(*tasks)
            print("[Supabase Agent Multi] Completed parallel actions =>", results)
        except Exception as e:
            print("[Supabase Agent Multi] Error in parallel actions =>", e)
            all_succeeded = False

        input("WHAT?c")
        if all_succeeded:
            # Check each action+result with our custom success criteria
            for action, result in zip(dispatchable_actions, results):
                if not self.check_action_success(action.action_type, result):
                    all_succeeded = False
                    break

        if all_succeeded:
            self.failed_count = 0
            # Only stop if STOP was present + everything else succeeded
            if stop_action_present:
                print("[Supabase Agent Multi] All actions succeeded + STOP => stopping now.")
                await self.output_queue.put(
                    ('exit_message', "Supabase Agent Multi has stopped.")
                )
                self.stop()
        else:
            # If anything failed, do not stop
            self.failed_count += 1
            if self.failed_count > self.retry_cap:
                self.stop()
            else:
                print("[Supabase Agent Multi] Some action(s) failed => continuing, not stopping.")

    @staticmethod
    def check_action_success(action_type: APIActionType, result: Any) -> bool:
        """
        A helper that decides if the action was successful by examining
        the result object returned from the handler. Different action types
        may require different checks, so adjust accordingly.
        """
        # 1) If the handler explicitly returned {'error': ...}, mark as failure:
        if isinstance(result, dict) and 'error' in result:
            return False

        # 2) For "delete" actions, check whether rows_deleted is nonzero
        if action_type in [APIActionType.SUPABASE_DELETE_CALENDAR_EVENT,
                           APIActionType.SUPABASE_DELETE_TASK]:
            if isinstance(result, dict) and result.get('rows_deleted', 0) == 0:
                return False

        # 3) For "update" actions, check for an updated record
        if action_type in [APIActionType.SUPABASE_UPDATE_CALENDAR_EVENT,
                           APIActionType.SUPABASE_UPDATE_TASK]:
            if isinstance(result, dict) and not result.get('id'):
                return False

        return True

    async def _dispatch_action(self, action: APIAction) -> Any:
        """
        Convert enumerated ID => real DB ID, attach user_id, then dispatch to supabase.
        """
        params = action.parameters or {}

        # If referencing enumerated "event_x" or "task_x", swap to real DB ID
        if "event_id" in params and params["event_id"] in self.event_id_map:
            params["event_id"] = self.event_id_map[params["event_id"]]
        if "task_id" in params and params["task_id"] in self.task_id_map:
            params["task_id"] = self.task_id_map[params["task_id"]]

        # Force the user_id internally, so the LLM never sees or modifies another user's data
        params["user_id"] = self.user_id

        # Execute
        return await self.supabase_handler.perform_action(
            APIAction(
                action_type=action.action_type,
                reason=action.reason,
                parameters=params
            )
        )

    def _format_enumerated_events(self, events):
        """
        Assign "event_1", "event_2", ...
        Store real ID in self.event_id_map.
        Omit user_id from the display entirely.
        """
        if not events:
            return "No future events found."

        self.event_id_map.clear()
        lines = []
        for i, evt in enumerate(events, start=1):
            enumerated = f"event_{i}"
            self.event_id_map[enumerated] = evt["id"]

            lines.append(f"{enumerated}:")
            lines.append(f"  name: {evt.get('name', '(no name)')}")
            desc = evt.get("description")
            if desc:
                lines.append(f"  description: {desc}")
            lines.append(f"  start: {evt['start']}")
            lines.append(f"  end: {evt['end']}")
            metadata = evt.get("metadata", {})
            if metadata:
                lines.append(f"  metadata: {metadata}")
            lines.append("")
        return "\n".join(lines)

    def _format_enumerated_tasks(self, tasks):
        """
        Assign "task_1", "task_2", ...
        Store real ID in self.task_id_map.
        Omit user_id from the display.
        """
        if not tasks:
            return "No future tasks found."

        self.task_id_map.clear()
        lines = []
        for i, tsk in enumerate(tasks, start=1):
            enumerated = f"task_{i}"
            self.task_id_map[enumerated] = tsk["id"]

            lines.append(f"{enumerated}:")
            lines.append(f"  name: {tsk.get('name', '(no name)')}")
            desc = tsk.get("description")
            if desc:
                lines.append(f"  description: {desc}")
            lines.append(f"  due: {tsk['due']}")
            status_str = "completed" if tsk.get("status") else "incomplete"
            lines.append(f"  status: {status_str}")

            metadata = tsk.get("metadata", {})
            if metadata:
                lines.append(f"  metadata: {metadata}")
            lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    # Example usage:
    agent = SupabaseCalendarTasksAPIAgentMulti(
        task="Add a new 'Clean my desk' task.",
        user_id="123e4567-e89b-12d3-a456-426614174000"
    )
    asyncio.run(agent.run())
