# gmail_api_agent.py

import json
import re
import os
import string

from api_agent_classes import APIAction, APIActionType
from api_agent import APIAgent
from api_llm_handling import AgentCall
from call_llm import call_llm

class GmailAPIAgent(APIAgent):
    def __init__(self, fast_mode=False, retry_cap=10):
        super().__init__(fast_mode=fast_mode, api="gmail", retry_cap=retry_cap)

        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join("api_prompts", "gmail_system.txt")
        self.gmail_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join("api_prompts", "gmail_user.txt")
        self.gmail_user_prompt_template = self.load_file(user_prompt_path)

    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def call_action(self, provider="cerebras", model="llama-3.3-70b") -> AgentCall:
        """
        Overridden to produce a specialized prompt for Gmail actions.
        """

        # Summarize the current memory of actions
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += f"- Step {i+1} => Called: {mem.call} | Received: {mem.received}\n"

        # The user request or final goal is in self.task, plus any self.task_notes
        # In your usage, you might have an AX tree or other placeholders.
        # We'll demonstrate an example with 'ax_tree' placeholder.
        user_replacements = {
            'memory': memory_text.strip(),
            'task': self.task if self.task else "",
            'task_notes': self.task_notes if self.task_notes else ""
        }

        # Perform string template substitution on the user prompt
        # e.g. if the text file references $memory, $task, etc.
        user_prompt_str = string.Template(self.gmail_user_prompt_template).substitute(user_replacements)

        # Call the LLM
        action_out_call = call_llm(
            system_content=self.gmail_system_prompt,
            user_content=user_prompt_str,
            model=model
        )

        # Convert LLM response -> APIAction
        chosen_action = None
        if action_out_call.parsed_output:
            try:
                ao = action_out_call.parsed_output
                action_type_str = ao.get("action_type", "").upper()

                if action_type_str == "STOP":
                    action_type = APIActionType.STOP
                elif action_type_str == "REQUEST_USER_INPUT":
                    action_type = APIActionType.REQUEST_USER_INPUT
                elif action_type_str == "GMAIL_LIST_MESSAGES":
                    action_type = APIActionType.GMAIL_LIST_MESSAGES
                elif action_type_str == "GMAIL_GET_MESSAGE":
                    action_type = APIActionType.GMAIL_GET_MESSAGE
                elif action_type_str == "GMAIL_SEND_EMAIL":
                    action_type = APIActionType.GMAIL_SEND_EMAIL
                elif action_type_str == "GMAIL_LIST_LABELS":
                    action_type = APIActionType.GMAIL_LIST_LABELS
                else:
                    action_type = APIActionType.STOP  # fallback

                chosen_action = APIAction(
                    action_type=action_type,
                    reason=ao.get("reason", "No reason provided"),
                    parameters=ao.get("parameters", None)
                )
            except Exception as e:
                print("Error extracting Gmail action from LLM:", e)

        # If we failed to parse or no valid action, default to STOP
        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned."
            )

        action_out_call.parsed_output = chosen_action
        return action_out_call
