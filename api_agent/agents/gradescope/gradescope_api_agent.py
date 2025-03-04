# gradescope_api_agent.py

import os
import string
import asyncio 

from api_agent import APIAgent
from api_agent_classes import APIAction, APIActionType, APILinearMemory
from api_llm_handling import AgentCall, LLMMessage
from call_llm import call_llm
from agents.gradescope.gradescope_api_handler import GradescopeAPIHandler

from typing import List, Tuple, Dict, Any

class GradescopeAPIAgent(APIAgent):
    def __init__(self, task="Track my Gradescope courses", fast_mode=False, retry_cap=10, credentials = None):
        """
        Initialize the GradescopeAPIAgent with a default task if none is provided.
        """
        super().__init__(fast_mode=fast_mode, api="gradescope", retry_cap=retry_cap, credentials = credentials)
        self.task = task  # You can override or set differently if desired
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, os.path.pardir, os.path.pardir, os.path.pardir))
        # Load the system prompt from a dedicated file
        system_prompt_path = os.path.join(project_root, "api_agent", "api_prompts", "gradescope", "gradescope_system.txt")
        self.gradescope_system_prompt = self.load_file(system_prompt_path)

        # Load the user prompt template from another file
        user_prompt_path = os.path.join(project_root, "api_agent", "api_prompts", "gradescope", "gradescope_user.txt")
        self.gradescope_user_prompt_template = self.load_file(user_prompt_path)
        self.poll_output = []
    def load_file(self, file_path: str) -> str:
        """Utility method to read the entire content of a text file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def initialize_api_handler(self):
        """Initialize the Gradescope API handler."""
        self.api_handler = GradescopeAPIHandler(self.credentials)

    async def setup(self):
        """
        Perform any setup tasks before the main run loop.
        If nothing special is needed, you can just pass.
        """
        pass

    async def call_action(
        self, provider="cerebras", model="llama-3.3-70b"
    ) -> AgentCall:
        """
        Asks the LLM to decide the next Gradescope action.
        Returns an AgentCall (which includes the chosen APIAction).
        """

        # Summarize the current memory of actions
        memory_text = ""
        for i, mem in enumerate(self.action_mem):
            memory_text += (
                f"- Step {i + 1} => Called: {mem.call} | Received: {mem.received}\n"
            )

        # Prepare user prompt replacements
        user_replacements = {
            "memory": memory_text.strip(),
            "task": self.task if self.task else "",
            "task_notes": self.task_notes if self.task_notes else "",
        }

        # Perform string template substitution on the user prompt
        user_prompt_str = string.Template(self.gradescope_user_prompt_template).substitute(
            user_replacements
        )

        print("[Gradescope Agent] Calling LLM for next action ...")

        # Call the LLM asynchronously
        agent_call = await call_llm(
            messages=[
                LLMMessage(message_role="system", content=self.gradescope_system_prompt),
                LLMMessage(message_role="user", content=user_prompt_str),
            ],
            provider=provider,
            model=model,
            max_tokens=8192,  # Adjust as needed
        )

        print("[Gradescope Agent] LLM response:", agent_call.llm_response)

        # Attempt to parse out the chosen action from the LLM
        chosen_action = None
        if agent_call.parsed_output:
            # Iterate through all parsed JSON blocks
            for parsed in agent_call.parsed_output:
                if isinstance(parsed, dict) and "action_type" in parsed:
                    try:
                        action_type_str = parsed.get("action_type", "").upper()
                        # Map the string to an APIActionType
                        action_type_mapping = {
                            "STOP": APIActionType.STOP,
                            "REQUEST_USER_INPUT": APIActionType.REQUEST_USER_INPUT,
                            "GRADESCOPE_LIST_COURSES": APIActionType.GRADESCOPE_LIST_COURSES,
                            "GRADESCOPE_LIST_ASSIGNMENTS": APIActionType.GRADESCOPE_LIST_ASSIGNMENTS,
                        }
                        action_type = action_type_mapping.get(
                            action_type_str,
                            APIActionType.STOP  # fallback to STOP if unrecognized
                        )

                        chosen_action = APIAction(
                            action_type=action_type,
                            reason=parsed.get("reason", "No reason provided"),
                            parameters=parsed.get("parameters", {}),
                        )
                        break  # Stop after we successfully parse one action
                    except Exception as e:
                        print("[Gradescope Agent] Error mapping action type:", e)
                        continue

        # If no valid action was parsed, default to STOP
        if not chosen_action:
            chosen_action = APIAction(
                action_type=APIActionType.STOP,
                reason="Failed to parse LLM action or no valid action returned.",
                parameters=None,
            )

        agent_call.parsed_output = chosen_action
        return agent_call

    async def handle_actions(self, action: APIAction):
        """
        Handle the chosen action returned from the LLM.
        """
        print(f"[Gradescope Agent] Handling action => {action.action_type} | Reason: {action.reason}")

        if action.action_type == APIActionType.STOP:
            # The LLM might provide a final_answer with sub-actions
            final_answer = []
            if action.parameters and isinstance(action.parameters, dict):
                final_answer = action.parameters.get("final_answer", [])

            if final_answer:
                print("[Gradescope Agent] STOP with final sub-actions => executing them now:")

                async def execute_sub_action(subaction_str: str, subparams: Any):
                    try:
                        sub_type_str = subaction_str.upper().strip()
                        # Map sub_type_str to an APIActionType for Gradescope
                        action_type_mapping = {
                            "REQUEST_USER_INPUT": APIActionType.REQUEST_USER_INPUT,
                            "GRADESCOPE_LIST_COURSES": APIActionType.GRADESCOPE_LIST_COURSES,
                            "GRADESCOPE_LIST_ASSIGNMENTS": APIActionType.GRADESCOPE_LIST_ASSIGNMENTS,
                        }
                        sub_action_type = action_type_mapping.get(sub_type_str, APIActionType.STOP)

                        # If subparams is just a single ID, wrap it in a dict if needed
                        # e.g. ["GRADESCOPE_LIST_ASSIGNMENTS", "12345"] -> {"course_id": "12345"}
                        if not isinstance(subparams, dict):
                            subparams = {"course_id": str(subparams)}

                        sub_action = APIAction(
                            action_type=sub_action_type,
                            reason="final_subaction",
                            parameters=subparams
                        )
                        await self._perform_gradescope_action(sub_action, is_final=True)
                    except Exception as e:
                        print("[Gradescope Agent] Error executing final sub-action:", e)

                # Execute all sub-actions in parallel
                tasks = [execute_sub_action(subaction_str, subparams) 
                        for (subaction_str, subparams) in final_answer]
                await asyncio.gather(*tasks)

            # Send a stop message to any listeners
            await self.output_queue.put(('exit_message', "Gradescope Agent has stopped."))
            self.stop()

        elif action.action_type == APIActionType.REQUEST_USER_INPUT:
            print("[Gradescope Agent] Received REQUEST_USER_INPUT action. Asking user ...")
            # Example: Ask user for additional information
            new_memory = APILinearMemory(
                self.api,
                call="REQUEST_USER_INPUT",
                received="User input placeholder"
            )
            self.action_mem.append(new_memory)

        else:
            await self._perform_gradescope_action(action)

    async def _perform_gradescope_action(self, action: APIAction, is_final: bool = False):
        """
        Dispatch a Gradescope API action and record the result in memory.
        """
        try:
            result = await self.api_handler.perform_action(action)
            # print(f"[Gradescope Agent] API call result: {result}")
            success = True
        except Exception as e:
            print(f"[Gradescope Agent] API call failed: {e}")
            success = False

        # Update memory if success/failure
        if not success:
            self.failed_count += 1
            if self.failed_count > self.retry_cap:
                print("[Gradescope Agent] Retry cap exceeded, stopping agent.")
                self.stop()
        else:
            self.failed_count = 0
            call_str = f"{action.action_type.value} with parameters {action.parameters}"
            new_memory = APILinearMemory(
                self.api,
                call=call_str,
                received=str(result)
            )
            if is_final:
                self.poll_output.append(new_memory)
            else:
                self.action_mem.append(new_memory)

    def get_poll_output(self):
        """
        Return a list of poll function calls and their outputs
        """
        return self.poll_output