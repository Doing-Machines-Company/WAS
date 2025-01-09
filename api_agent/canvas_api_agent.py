# canvas_api_agent.py

import os
import string

from api_agent_classes import APIAction, APIActionType
from api_llm_handling import AgentCall
from call_llm import call_llm

from api_agent import APIAgent


class CanvasAPIAgent(APIAgent):
    def __init__(self, fast_mode=False, retry_cap=10):
        super().__init__(fast_mode=fast_mode, api="canvas", retry_cap=retry_cap)

        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join("api_prompts", "canvas_system.txt")
        self.canvas_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join("api_prompts", "canvas_user.txt")
        self.canvas_user_prompt_template = self.load_file(user_prompt_path)

    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    async def call_action(
        self, provider="cerebras", model="llama-3.3-70b"
    ) -> AgentCall:
        """
        Overridden to produce a specialized prompt for Canvas actions.
        """

        # Summarize the current memory of actions
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += (
                f"- Step {i+1} => Called: {mem.call} | Received: {mem.received}\n"
            )

        # The user request or final goal is in self.task, plus any self.task_notes
        user_replacements = {
            "memory": memory_text.strip(),
            "task": self.task if self.task else "",
            "task_notes": self.task_notes if self.task_notes else "",
        }

        # Substitute placeholders in the user prompt
        user_prompt_str = string.Template(self.canvas_user_prompt_template).substitute(
            user_replacements
        )

        # Call the LLM
        action_out_call = call_llm(
            system_content=self.canvas_system_prompt,
            user_content=user_prompt_str,
            model=model,
        )

        chosen_action = None
        if action_out_call.parsed_output:
            try:
                ao = action_out_call.parsed_output
                action_type_str = ao.get("action_type", "").upper()

                if action_type_str == "STOP":
                    action_type = APIActionType.STOP
                elif action_type_str == "REQUEST_USER_INPUT":
                    action_type = APIActionType.REQUEST_USER_INPUT
                elif action_type_str == "CANVAS_LIST_ASSIGNMENTS":
                    action_type = APIActionType.CANVAS_LIST_ASSIGNMENTS
                elif action_type_str == "CANVAS_GET_ASSIGNMENT_DETAILS":
                    action_type = APIActionType.CANVAS_GET_ASSIGNMENT_DETAILS
                elif action_type_str == "CANVAS_LIST_MODULES":
                    action_type = APIActionType.CANVAS_LIST_MODULES
                elif action_type_str == "CANVAS_GET_MODULE_ITEMS":
                    action_type = APIActionType.CANVAS_GET_MODULE_ITEMS
                elif action_type_str == "CANVAS_GET_GRADES":
                    action_type = APIActionType.CANVAS_GET_GRADES
                elif action_type_str == "CANVAS_GET_SUBMISSION_HISTORY":
                    action_type = APIActionType.CANVAS_GET_SUBMISSION_HISTORY
                else:
                    action_type = APIActionType.STOP

                chosen_action = APIAction(
                    action_type=action_type,
                    reason=ao.get("reason", "No reason provided"),
                    parameters=ao.get("parameters", None),
                )
            except Exception as e:
                print("Error extracting Canvas action from LLM:", e)

        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
            )

        action_out_call.parsed_output = chosen_action
        return action_out_call
