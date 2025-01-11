# gmail_api_agent.py

import os
import string

from api_agent_classes import APIAction, APIActionType
from api_agent import APIAgent
from api_llm_handling import AgentCall, LLMMessage
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

    async def call_action(self, provider: str = "cerebras", model: str = "llama-3.3-70b") -> AgentCall:
        """
        Produces a specialized prompt for Gmail actions and processes the LLM response.

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
        user_prompt_str = string.Template(self.gmail_user_prompt_template).substitute(user_replacements)

        # Build LLM messages
        messages = [
            LLMMessage(message_role="system", content=self.gmail_system_prompt),
            LLMMessage(message_role="user", content=user_prompt_str),
        ]

        print("GOT HERE 1")

        # Call the LLM asynchronously
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=512  # Adjust as needed
        )

        print(agent_call.llm_response)

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
                            "GMAIL_LIST_MESSAGES": APIActionType.GMAIL_LIST_MESSAGES,
                            "GMAIL_GET_MESSAGE": APIActionType.GMAIL_GET_MESSAGE,
                            "GMAIL_SEND_EMAIL": APIActionType.GMAIL_SEND_EMAIL,
                            "GMAIL_LIST_LABELS": APIActionType.GMAIL_LIST_LABELS,
                            "GMAIL_DELETE_MESSAGE": APIActionType.GMAIL_DELETE_MESSAGE, # isn't in prompt
                            "GMAIL_MODIFY_MESSAGE": APIActionType.GMAIL_MODIFY_MESSAGE # isn't in prompt
                        }

                        action_type = action_type_mapping.get(action_type_str, APIActionType.STOP)  # Fallback to STOP

                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", None)
                        )
                        print(f"API ACTION SAFETY: {chosen_action.is_safe}")
                        break  # Exit after finding the first valid action
                    except Exception as e:
                        print("Error mapping Gmail action type:", e)
                        continue  # Try the next parsed JSON block

        # If no valid action was parsed, default to STOP ?????
        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
                parameters=None
            )

        # Update the parsed_output with the chosen_action
        agent_call.parsed_output = chosen_action

        return agent_call


if __name__ == "__main__":
    import asyncio

    # Instantiate an agent for Gmail
    agent = GmailAPIAgent()

    # Actually run the agent’s async loop
    asyncio.run(agent.run())
