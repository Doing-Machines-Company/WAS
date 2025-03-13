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
        self.current_datetime = datetime.now(timezone.utc).isoformat()

        # Will hold the user's calendar list (all available)
        self.all_calendars = []

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

    def initialize_api_handler(self, credentials = None):
        """Initialize the Google Calendar API handler."""
        self.api_handler = GoogleCalendarAPIHandler(credentials)

    async def setup(self):
        """
        Setup tasks:
          - fetch all available calendars and store them in self.all_calendars
        """
        # We'll do an immediate CALENDAR_LIST_CALENDARS action
        try:
            list_action = APIAction(
                action_type=APIActionType.CALENDAR_LIST_CALENDARS,
                reason="Fetch all calendars for context",
                parameters={}
            )
            result = self.api_handler.perform_action(list_action)
            if isinstance(result, list):
                self.all_calendars = result
            else:
                self.all_calendars = []
        except Exception as e:
            print("Error fetching all calendars:", e)
            self.all_calendars = []

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
            # NEW: pass the entire list of calendars as a string
            'available_calendars': str(self.all_calendars)
        }

        user_prompt_str = string.Template(self.gmail_user_prompt_template).substitute(user_replacements)

        # print(user_prompt_str)
        # input("CHECK!")

        # Also substitute $current_datetime into the system prompt
        system_prompt_str = string.Template(self.gmail_system_prompt).substitute({
            'current_datetime': self.current_datetime
        })

        # Build LLM messages
        messages = [
            LLMMessage(message_role="system", content=system_prompt_str),
            LLMMessage(message_role="user", content=user_prompt_str),
        ]

        print("[GCal Agent] Preparing to call LLM for action determination.")

        # Call the LLM
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=512
        )

        print(f"[GCal Agent] LLM Response: {agent_call.llm_response}")

        chosen_action = None
        if agent_call.parsed_output:
            for parsed in agent_call.parsed_output:
                if isinstance(parsed, dict) and "action_type" in parsed:
                    try:
                        action_type = APIActionType.from_string(parsed["action_type"])
                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", None)
                        )
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

        agent_call.parsed_output = [chosen_action]
        return agent_call

    async def handle_actions(self, actions: list[APIAction]):
        """
        Execute or handle the given APIAction.
        """
        action = actions[0]
        action_type = action.action_type
        action_reason = action.reason

        print(f"[GCal Agent] Handling action: {action_type} | Reason: {action_reason}")

        if action_type == APIActionType.STOP:
            final_answer = []
            if action.parameters:
                final_answer = action.parameters.get("final_answer", [])

            # Execute final sub-actions if any
            if final_answer:
                print("[GCal Agent] STOP with final sub-actions => executing them now:")
                for idx, (subaction_str, subparams) in enumerate(final_answer, start=1):
                    subaction_type = APIActionType.from_string(subaction_str)
                    print(f"  - Sub-action {idx}: {subaction_type}")
                    try:
                        result = self.api_handler.perform_action(APIAction(
                            action_type=subaction_type,
                            reason="Final batch sub-action",
                            parameters=subparams
                        ))
                        print("    Sub-action result:", result)
                    except Exception as e:
                        print("    Sub-action error:", e)

            await self.output_queue.put(('exit_message', "GCal Agent has stopped."))
            self.stop()

        else:
            # Perform the single Calendar action
            try:
                result = self.api_handler.perform_action(action)
                success = True
                print(f"[GCal Agent] API call result: {result}")
            except Exception as e:
                print(f"[GCal Agent] API call failed: {e}")
                success = False

            if not success:
                self.failed_count += 1
                if self.failed_count > self.retry_cap:
                    self.stop()
            else:
                self.failed_count = 0
                # Store the action and result in memory
                call_str = f"{action_type.value} with parameters: {action.parameters}"
                new_memory = APILinearMemory(
                    self.api,
                    call=call_str,
                    received=str(result)
                )
                self.action_mem.append(new_memory)


if __name__ == "__main__":
    # Example usage
    agent = GCalAPIAgent(task="What 210 events do I have?")
    asyncio.run(agent.run())
