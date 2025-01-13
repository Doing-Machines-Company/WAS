# gmail_api_agent.py

import os
import string
import asyncio

from api_agent_classes import APIAction, APIActionType, APILinearMemory
from api_agent import APIAgent
from api_llm_handling import AgentCall, LLMMessage
from call_llm import call_llm
from api_functions import GmailAPIHandler

class GmailAPIAgent(APIAgent):
    def __init__(self, task="", fast_mode=False, retry_cap=10):
        super().__init__(fast_mode=fast_mode, api="gmail", retry_cap=retry_cap)

        self.task = "what are my emails"

        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join("api_prompts/gmail", "gmail_system.txt")
        self.gmail_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join("api_prompts/gmail", "gmail_user.txt")
        self.gmail_user_prompt_template = self.load_file(user_prompt_path)

    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def initialize_api_handler(self):
        """Initialize the Gmail API handler."""
        return GmailAPIHandler()

    async def setup(self):
        """Setup tasks specific to GmailAPIAgent."""
        pass

    def initialize_index(self):
        """Create an LLM-based index over some reference text (for clarifications, etc.)."""
        # Implementation specific to Gmail, e.g., indexing emails or labels
        # Placeholder for actual indexing logic
        pass

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

        print("Preparing to call LLM for action determination.")

        # Call the LLM asynchronously
        agent_call = await call_llm(
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=512  # Adjust as needed
        )

        print(f"LLM Response: {agent_call.llm_response}")

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
                            "GMAIL_DELETE_MESSAGE": APIActionType.GMAIL_DELETE_MESSAGE,
                            "GMAIL_MODIFY_MESSAGE": APIActionType.GMAIL_MODIFY_MESSAGE
                        }

                        action_type = action_type_mapping.get(action_type_str, APIActionType.STOP)  # Fallback to STOP

                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", None)
                        )
                        print(f"Chosen APIAction: {chosen_action.action_type} | Reason: {chosen_action.reason}")
                        break  # Exit after finding the first valid action
                    except Exception as e:
                        print("Error mapping Gmail action type:", e)
                        continue  # Try the next parsed JSON block

        # If no valid action was parsed, default to STOP
        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
                parameters=None
            )

        # Update the parsed_output with the chosen_action
        agent_call.parsed_output = chosen_action

        return agent_call

    async def handle_actions(self, action: APIAction):
        """
        Handle the given APIAction. This includes executing the action using the API handler,
        managing user interactions, and updating memory.

        Args:
            action (APIAction): The action to handle.
        """
        action_type = action.action_type
        action_reason = action.reason

        print(f"Handling APIAction: {action_type} | Reason: {action_reason}")

        if action_type == APIActionType.STOP:
            # End agent
            await self.output_queue.put(('exit_message', "Gmail Agent has stopped."))
            self.stop()

        elif action_type == APIActionType.REQUEST_USER_INPUT:
            # Ask user for specific input
            question = action.parameters.get("question", "Please provide additional information.")
            user_input = await self.ask_user(question)

            # Store the response in context
            self.context_info += f"User input: {user_input}\n"
            self.question_answers.append((question, user_input))

            # Record the action in memory
            new_memory = APILinearMemory(
                self.api,
                call="REQUEST_USER_INPUT",
                received=user_input
            )
            self.action_mem.append(new_memory)

        else:
            # Perform the API action using the API handler
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
                # Store the action in memory
                new_memory = APILinearMemory(
                    self.api,
                    call=action_type.value,
                    received=str(result)
                )
                self.action_mem.append(new_memory)

if __name__ == "__main__":

    # Instantiate an agent for Gmail
    agent = GmailAPIAgent()

    # Actually run the agent’s async loop
    asyncio.run(agent.run())
