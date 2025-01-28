# gcal_api_agent.py

import os
import string
import asyncio
from datetime import datetime, timezone

from api_agent_classes import APIAction, APIActionType, APILinearMemory
from api_agent import APIAgent
from api_llm_handling import AgentCall, LLMMessage
from call_llm import call_llm
from api_functions import GoogleCalendarAPIHandler


class GCalAPIAgent(APIAgent):
    def __init__(self, task="", fast_mode=False, retry_cap=10):
        super().__init__(fast_mode=fast_mode, api="google_calendar", retry_cap=retry_cap)

        self.task = task

        # Store current date/time in ISO format (UTC) for the LLM's awareness.
        self.current_datetime = datetime.now(timezone.utc).isoformat()

        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join("api_prompts/gcal", "google_calendar_system.txt")
        self.gmail_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join("api_prompts/gcal", "google_calendar_user.txt")
        self.gmail_user_prompt_template = self.load_file(user_prompt_path)

    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def initialize_api_handler(self):
        """Initialize the Google Calendar API handler."""
        return GoogleCalendarAPIHandler()

    async def setup(self):
        """Setup tasks specific to GCalAPIAgent (none needed)."""
        pass

    def initialize_index(self):
        """Not used here."""
        pass

    async def call_action(self, provider: str = "anthropic", model: str = "claude-3-5-sonnet-latest") -> AgentCall:
        """
        Produces a specialized prompt for Google Calendar actions and processes the LLM response.
        """
        # Summarize the current memory of actions
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += f"- Step {i + 1} => Called: {mem.call} | Received: {mem.received}\n"

        # Prepare user prompt placeholders
        user_replacements = {
            'memory': memory_text.strip(),
            'task': self.task if self.task else "",
            'task_notes': self.task_notes if self.task_notes else ""
        }
        user_prompt_str = string.Template(self.gmail_user_prompt_template).substitute(user_replacements)

        # Also substitute $current_datetime into the system prompt
        system_prompt_str = string.Template(self.gmail_system_prompt).substitute({
            'current_datetime': self.current_datetime
        })

        # Build LLM messages
        messages = [
            LLMMessage(message_role="system", content=system_prompt_str),
            LLMMessage(message_role="user", content=user_prompt_str),
        ]

        print("Preparing to call LLM for action determination.")

        # Call the LLM
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=512  # Adjust as needed
        )

        print(f"LLM Response: {agent_call.llm_response}")

        chosen_action = None

        if agent_call.parsed_output:
            for parsed in agent_call.parsed_output:
                if isinstance(parsed, dict) and "action_type" in parsed:
                    try:
                        action_type_str = parsed.get("action_type", "").upper()
                        # Map string -> APIActionType
                        action_type_mapping = {
                            "STOP": APIActionType.STOP,
                            "CALENDAR_LIST_CALENDARS": APIActionType.CALENDAR_LIST_CALENDARS,
                            "CALENDAR_CREATE_EVENT": APIActionType.CALENDAR_CREATE_EVENT,
                            "CALENDAR_LIST_EVENTS": APIActionType.CALENDAR_LIST_EVENTS,
                            "CALENDAR_UPDATE_EVENT": APIActionType.CALENDAR_UPDATE_EVENT,
                            "CALENDAR_DELETE_EVENT": APIActionType.CALENDAR_DELETE_EVENT,
                        }
                        action_type = action_type_mapping.get(action_type_str, APIActionType.STOP)

                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", None)
                        )
                        print(f"Chosen APIAction: {chosen_action.action_type} | Reason: {chosen_action.reason}")
                        break

                    except Exception as e:
                        print("Error mapping Calendar action type:", e)
                        continue

        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
                parameters=None
            )

        agent_call.parsed_output = chosen_action
        return agent_call

    async def handle_actions(self, action: APIAction):
        """
        Execute or handle the given APIAction.
        No 'REQUEST_USER_INPUT' is handled here.
        """
        action_type = action.action_type
        action_reason = action.reason

        print(f"Handling APIAction: {action_type} | Reason: {action_reason}")

        if action_type == APIActionType.STOP:
            # The agent is done.
            final_answer = []
            if action.parameters:
                final_answer = action.parameters.get("final_answer", [])

            if final_answer:
                print("Executing final sub-actions from STOP:")
                for idx, (subaction_str, subparams) in enumerate(final_answer, start=1):
                    subaction_type = APIActionType.from_string(subaction_str)
                    print(f"{idx}. {subaction_str} => {subparams}")
                    try:
                        # Optionally perform each sub-action
                        result = self.api_handler.perform_action(APIAction(
                            action_type=subaction_type,
                            reason="Final batch sub-action",
                            parameters=subparams
                        ))
                        print("   Sub-action result:", result)
                    except Exception as e:
                        print("   Sub-action error:", e)

            await self.output_queue.put(('exit_message', "GCal Agent has stopped."))
            self.stop()

        else:
            # Perform the single-step Calendar action
            try:
                result = self.api_handler.perform_action(action)
                success = True
                print(f"API call result: {result}")
            except Exception as e:
                print(f"API call failed: {e}")
                success = False

            if not success:
                self.failed_count += 1
                if self.failed_count > self.retry_cap:
                    self.stop()
            else:
                self.failed_count = 0
                # Store the action and result in memory
                new_memory = APILinearMemory(
                    self.api,
                    call=action_type.value,
                    received=str(result)
                )
                self.action_mem.append(new_memory)


if __name__ == "__main__":
    # Example usage
    # Instantiate an agent for Google Calendar
    agent = GCalAPIAgent(task="create two all-day events on Jan 28, 2025, called 'one' and 'two'")
    asyncio.run(agent.run())
