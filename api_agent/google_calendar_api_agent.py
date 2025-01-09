# google_calendar_api_agent.py

import os
import string

from api_agent_classes import APIAction, APIActionType
from api_agent import APIAgent
from api_llm_handling import AgentCall, LLMMessage
from call_llm import call_llm

class GoogleCalendarAPIAgent(APIAgent):
    def __init__(self, fast_mode=False, retry_cap=10):
        super().__init__(fast_mode=fast_mode, api="google_calendar", retry_cap=retry_cap)

        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join("api_prompts", "calendar_system.txt")
        self.calendar_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join("api_prompts", "calendar_user.txt")
        self.calendar_user_prompt_template = self.load_file(user_prompt_path)

    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def call_action(self, provider: str = "cerebras", model: str = "llama-3.3-70b") -> AgentCall:
        """
        Produces a specialized prompt for Google Calendar actions and processes the LLM response.

        Args:
            provider (str): The LLM provider to use.
            model (str): The model name to use.

        Returns:
            AgentCall: The result of the LLM call, including the chosen action.
        """
        # Summarize the current memory of actions
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += f"- Step {i + 1} => Called: {mem.call} | Received: {mem.received}\n"

        # Prepare user prompt replacements
        user_replacements = {
            'memory': memory_text.strip(),
            'task': self.task if self.task else "",
            'task_notes': self.task_notes if self.task_notes else ""
        }

        # Perform string template substitution on the user prompt
        user_prompt_str = string.Template(self.calendar_user_prompt_template).substitute(user_replacements)

        # Build LLM messages
        messages = [
            LLMMessage(message_role="system", content=self.calendar_system_prompt),
            LLMMessage(message_role="user", content=user_prompt_str),
        ]

        # Call the LLM asynchronously
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=512  # Adjust as needed
        )

        chosen_action = None

        # Process parsed_output
        if agent_call.parsed_output:
            # Iterate through all parsed JSON blocks
            for parsed in agent_call.parsed_output:
                if isinstance(parsed, dict) and "action_type" in parsed:
                    try:
                        action_type_str = parsed.get("action_type", "").upper()

                        # Map action_type_str to APIActionType Enum
                        action_type_mapping = {
                            "STOP": APIActionType.STOP,
                            "REQUEST_USER_INPUT": APIActionType.REQUEST_USER_INPUT,
                            "CALENDAR_LIST_CALENDARS": APIActionType.CALENDAR_LIST_CALENDARS,
                            "CALENDAR_CREATE_EVENT": APIActionType.CALENDAR_CREATE_EVENT,
                            "CALENDAR_LIST_EVENTS": APIActionType.CALENDAR_LIST_EVENTS,
                            "CALENDAR_UPDATE_EVENT": APIActionType.CALENDAR_UPDATE_EVENT,
                            "CALENDAR_DELETE_EVENT": APIActionType.CALENDAR_DELETE_EVENT,
                        }

                        action_type = action_type_mapping.get(action_type_str, APIActionType.STOP)  # Fallback to STOP

                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", None)
                        )
                        break  # Exit after finding the first valid action
                    except Exception as e:
                        print("Error mapping Calendar action type:", e)
                        continue  # Try the next parsed JSON block

        # If no valid action was parsed, default to STOP ????
        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
                parameters=None
            )

        # Update the parsed_output with the chosen_action
        agent_call.parsed_output = chosen_action

        return agent_call

