# api_agent.py

import asyncio
import copy
import datetime
import gc
import os
import pickle
import time

from api_agent_classes import APIAction, APIActionType, APILinearMemory, APIType
from api_functions import CanvasAPIHandler, GmailAPIHandler, GoogleCalendarAPIHandler
from api_llm_handling import AgentCall
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode

from inferenceagent import (
    call_intermediate_questions_agent,
    call_task_separator,
    call_unified_task_clarifier,
)
from utils.trajectory_saves import SavedTrajectory, SavedTrajectoryNode


class APIAgent:
    def __init__(self, fast_mode=False, api="gmail", retry_cap=10):
        """Initialize an API-based LLM agent."""
        self.api = APIType.from_string(api)

        # Control events
        self.stop_event = asyncio.Event()
        self.cleaned_up = asyncio.Event()

        self.fast_mode = fast_mode
        self.retry_cap = retry_cap

        # Inputs or prompts
        self.task = None  # The main user request
        self.task_notes = ""  # Additional context

        # For LLM question/answer flows
        self.questions = []
        self.question_answers = []

        # For memory, record all calls
        self.action_mem = []

        # Hidden or default fields for user
        self.hidden_inputs = []

        # Queues for user I/O
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()

        # Track attempts
        self.failed_count = 0
        self.reload_count = 0

        # For storing entire conversation
        self.saved_trajectory = SavedTrajectory()
        self.curr_save_node = None

        # Additional context from knowledge base
        self.context_info = ""
        self.item_context_pairs = ""

        # Initialize the LLM index
        self.initialize_index()

        # Initialize the correct API handler
        if self.api == APIType.GMAIL:
            self.api_handler = GmailAPIHandler()
        elif self.api == APIType.GOOGLE_CALENDAR:
            self.api_handler = GoogleCalendarAPIHandler()
        elif self.api == APIType.CANVAS:
            self.api_handler = CanvasAPIHandler()
        else:
            raise ValueError(f"No handler available for API: {api}")

    def initialize_index(self):
        """Create an LLM-based index over some reference text (for clarifications, etc.)."""
        start = time.time()
        with open("./data/factsNEW.txt", "r") as f:
            doc = f.read()

        chunks = doc.split("***")
        nodes = [TextNode(text=chunk, id_=i) for i, chunk in enumerate(chunks)]
        self.index = VectorStoreIndex(nodes)
        self.retriever = self.index.as_retriever(
            vector_store_query_mode="mmr", vector_store_kwargs={"mmr_threshold": 1}
        )
        print("Index created in", time.time() - start, "seconds.")

    async def ask_user(self, question):
        """Ask the user a question asynchronously; wait for a response."""
        await self.output_queue.put(("question", question))
        while not self.stop_event.is_set():
            try:
                return await asyncio.wait_for(self.input_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
        raise InterruptedError("Agent stopped")

    async def formulate_questions(self):
        """Use LLM calls to figure out clarifying questions about the user's task."""
        # 1) Retrieve context
        retrieved = self.retriever.retrieve(self.task)
        self.context_info = "\n".join([node.get_content() for node in retrieved])

        # 2) Identify interesting items
        sep_call = await call_task_separator(self.task)
        interesting_items = sep_call.parsed_output if sep_call.parsed_output else []

        # 3) Build item-context pairs
        def autoregressive_retrieve(query, k=2):
            new_task = query
            nodes = []
            for i in range(k):
                sub_retriever = self.index.as_retriever(similarity_top_k=i + 1)
                new_node = sub_retriever.retrieve(new_task)[-1]
                new_task += new_node.get_content()
                nodes.append(new_node)
            return nodes

        pairs = []
        for item in interesting_items:
            sub_nodes = autoregressive_retrieve(item, k=2)
            context_str = "".join(n.get_content() for n in sub_nodes)
            pairs.append(f"Item: {item}\nContext: {context_str}")
        self.item_context_pairs = "\n\n".join(pairs)

        self.saved_trajectory.important_info = self.item_context_pairs

        # Possibly load a known set of clarifying questions
        def read_questions():
            with open("data/questions.txt", "r") as f:
                return f.read()

        question_text = await asyncio.to_thread(read_questions)

        # Let an LLM unify and figure out the best clarifying questions
        clarifier_call = await call_unified_task_clarifier(self.task, question_text)
        self.questions = (
            clarifier_call.parsed_output if clarifier_call.parsed_output else []
        )

    async def call_action(self, provider, model) -> AgentCall:
        """
        This is intentionally left as a placeholder now, because each specialized
        agent (Gmail or Google Calendar) will override it.

        If called here directly, raise a NotImplementedError.
        """
        raise NotImplementedError(
            "Use a specialized agent subclass that implements call_action()."
        )

    async def run(self):
        """Main execution loop for the agent."""

        self.task = "What emails did I get today (Jan 8 2025)?"
        self.task_notes = ""

        # # 1) If no task is set, ask user
        # if self.task is None:
        #     self.task = await self.ask_user("What do you want to do with the API(s)?")
        #     self.saved_trajectory.user_input_task = self.task
        #
        # # 2) Formulate clarifying questions
        # if not self.stop_event.is_set():
        #     await self.formulate_questions()
        #     for q in self.questions:
        #         if self.stop_event.is_set():
        #             break
        #         ans = await self.ask_user(q)
        #         self.question_answers.append((q, ans))
        #
        # self.saved_trajectory.question_answers = self.question_answers
        #
        # # 3) Clean up user queries and build final self.task
        # if not self.stop_event.is_set():
        #     qclean_call = await call_unified_question_cleaner(self.task, self.question_answers)
        #     if qclean_call.parsed_output:
        #         self.task = qclean_call.parsed_output
        #
        #     context_call = await call_unified_context_cleaner(
        #         self.task, self.task_notes, self.context_info
        #     )
        #     if context_call.parsed_output:
        #         self.task_notes = context_call.parsed_output

        # 4) Loop to process chosen actions from LLM
        while not self.stop_event.is_set():
            try:
                self.curr_save_node = SavedTrajectoryNode()

                # a) LLM decides on next action => we get an `APIAction`
                # NOTE: specialized classes override call_action(...)
                action_out_call = await self.call_action(
                    provider="cerebras", model="llama-3.3-70b"
                )
                chosen_action: APIAction = action_out_call.parsed_output

                if not chosen_action:
                    # If it's None or empty, we don't know what to do, treat as failure
                    self.failed_count += 1
                    if self.failed_count > self.retry_cap:
                        self.stop()
                    break

                self.curr_save_node.ad_call = action_out_call
                action_type = chosen_action.action_type
                action_reason = chosen_action.reason

                print(f"Chosen APIAction: {action_type} | Reason: {action_reason}")

                # b) Handle special vs. API action
                if action_type == APIActionType.STOP:
                    # End agent
                    await self.output_queue.put(("exit_message", "Agent has stopped."))
                    self.stop()
                    break

                elif action_type == APIActionType.REQUEST_USER_INPUT:
                    # The agent wants additional user input
                    intermediate_call = await call_intermediate_questions_agent(
                        self.task,
                        "",  # optionally pass partial context
                        action_reason,
                        self.task_notes,
                    )
                    inter_questions = intermediate_call.parsed_output or []
                    for qq in inter_questions:
                        if self.stop_event.is_set():
                            break
                        _ = await self.ask_user(qq)

                    # Record that we asked the user for input
                    new_memory = APILinearMemory(
                        self.api,
                        call="request_user_input",
                        received="Collected user input",
                    )
                    self.action_mem.append(new_memory)

                else:
                    # Perform the call using the chosen action type & parameters
                    result = "result didn't update"
                    try:
                        result = self.api_handler.perform_action(chosen_action)
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
                            self.api, call=action_type.value, received=str(result)
                        )
                        self.action_mem.append(new_memory)

                # d) Save step
                self.saved_trajectory.add_node(copy.deepcopy(self.curr_save_node))

                gc.collect()

            except Exception as e:
                print(f"Agent encountered exception: {e}")
                # If a stop is triggered, do final cleanup
                if self.stop_event.is_set():
                    await self.cleanup()
                else:
                    self.failed_count += 1
                    if self.failed_count > self.retry_cap:
                        self.stop()
            finally:
                if self.stop_event.is_set():
                    await self.cleanup()

    async def cleanup(self):
        """Cleanup any resources if needed."""
        gc.collect()
        self.cleaned_up.set()

    def stop(self):
        """Stop execution and save the trajectory to disk."""
        now = datetime.datetime.now()
        filename = (
            f"{self.saved_trajectory.user_input_task}_{now.strftime('%Y%m%d_%H%M')}.pkl"
        )
        directory = "saved_trajectories"
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, filename), "wb") as f:
            pickle.dump(self.saved_trajectory, f)
        self.stop_event.set()
