import os
import pickle
import time
import copy
import asyncio
import gc
import datetime

from llama_index.core.schema import TextNode
from llama_index.core import VectorStoreIndex

from utils.trajectory_saves import SavedTrajectory, SavedTrajectoryNode
from utils.inference_data import Action, IndefiniteAction
from inferenceagent import (
    call_task_separator,
    call_unified_task_clarifier,
    call_unified_question_cleaner,
    call_unified_context_cleaner,
    call_unified_notes_cleaner,
    call_intermediate_questions_agent,
    call_input_agent,
    call_action_part1,
    call_action_part2,
    AgentCall
)
from api_agent_classes import (
    APILinearMemory,
    APIType
)

'''

class APIType(Enum):
    SPECIAL = "special"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"

@dataclass
class APILinearMemory:
    api_type: APIType
    call: str
    received: str

'''


    


'''

Used for a single website's API, perhaps we can just do *all* APIs, but may degrade performance too much.
I.e., one ApiAgent for gmail, one for Canvas.etc

(should?) We should persist this agent until it's no longer needed

'''
class ApiAgent:
    def __init__(self, fast_mode=False, retry_cap=10):
        """Initialize an API-based LLM agent."""
        self.stop_event = asyncio.Event()
        self.cleaned_up = asyncio.Event()

        self.fast_mode = fast_mode
        self.retry_cap = retry_cap

        # Inputs or prompts
        self.task = None  # API SPECIFIC TASK
        self.task_notes = ''

        # For LLM question/answer flows
        self.questions = []
        self.question_answers = []

        # For memory, lossless
        self.action_mem = []

        # If you want hidden or default fields for the user:
        self.hidden_inputs = []

        # Queues for user I/O
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()

        # Track attempts and partial results
        self.failed_count = 0
        self.reload_count = 0

        # For storing entire conversation or process
        self.saved_trajectory = SavedTrajectory()
        self.curr_save_node = None

        # Additional context from a knowledge base
        self.context_info = ""
        self.item_context_pairs = ""

        self.initialize_index()
        self.init_special_actions()

    def initialize_index(self):
        """Create an LLM-based index over some reference text (for clarifications, etc.)."""
        start = time.time()
        with open('./data/factsNEW.txt', 'r') as f:
            doc = f.read()

        chunks = doc.split('***')
        nodes = [TextNode(text=chunk, id_=i) for i, chunk in enumerate(chunks)]
        self.index = VectorStoreIndex(nodes)
        self.retriever = self.index.as_retriever(
            vector_store_query_mode="mmr",
            vector_store_kwargs={"mmr_threshold": 1}
        )
        print("Index created in", time.time() - start, "seconds.")

    async def ask_user(self, question):
        """Ask the user a question asynchronously; wait for a response."""
        await self.output_queue.put(('question', question))
        while not self.stop_event.is_set():
            try:
                return await asyncio.wait_for(self.input_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
        raise InterruptedError("Agent stopped")

    async def formulate_questions(self):
        """Use your LLM calls to figure out what clarifying questions to ask about the user's API task."""
        # Retrieve context
        retrieved = self.retriever.retrieve(self.task)
        self.context_info = "\n".join([node.get_content() for node in retrieved])

        # Identify interesting items
        sep_call = await call_task_separator(self.task)
        interesting_items = sep_call.parsed_output if sep_call.parsed_output else []

        # Build item-context pairs
        def autoregressive_retrieve(query, k=2):
            new_task = query
            nodes = []
            for i in range(k):
                sub_retriever = self.index.as_retriever(similarity_top_k=i + 1)
                # last retrieved node
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

        # Load a known set of clarifying questions from disk
        def read_questions():
            with open('data/questions.txt', 'r') as f:
                return f.read()
        question_text = await asyncio.to_thread(read_questions)

        # Let an LLM unify and figure out the best clarifying questions
        clarifier_call = await call_unified_task_clarifier(self.task, question_text)
        self.questions = clarifier_call.parsed_output if clarifier_call.parsed_output else []

    async def action_call(self, provider, model) -> AgentCall:
        """
        WILL USE task_notes and action_mem
        """
        start_time = time.time()
        # TODO for APIs
        print("Chained action call total time:", time.time() - start_time)
        return None

    def init_special_actions(self):
        """Define special action types like STOP, RELOAD, ASK_USER, etc."""
        stop_action = Action(Action.Type.STOP, None, None)
        stop_action.set_special_effect('STOP')
        stop_indefinite = IndefiniteAction(
            [Action.Type.STOP], stop_action, None, IndefiniteAction.Location.SPECIAL
        )

        input_action = Action(Action.Type.INPUT_GIVEN_INTENT, None, None)
        input_action.set_special_effect('WRITE TEXT MODE')
        input_indefinite = IndefiniteAction(
            [Action.Type.INPUT_GIVEN_INTENT], input_action, None, IndefiniteAction.Location.SPECIAL
        )

        ask_action = Action(Action.Type.REQUEST_USER_INPUT, None, None)
        ask_action.set_special_effect('ASK USER')
        ask_indefinite = IndefiniteAction(
            [Action.Type.REQUEST_USER_INPUT], ask_action, None, IndefiniteAction.Location.SPECIAL
        )


        # You could store them if you want custom logic around them
        self.special_actions = [
            stop_indefinite,
            input_indefinite,
            ask_indefinite,
        ]

    async def run(self):
        """Main execution loop for the agent."""
        # 1) If no task is set, ask the user
        if self.task is None:
            self.task = await self.ask_user("What do you want to do with the API(s)?")
            self.saved_trajectory.user_input_task = self.task

        # 2) Formulate clarifying questions
        if not self.stop_event.is_set():
            await self.formulate_questions()
            for q in self.questions:
                if self.stop_event.is_set():
                    break
                ans = await self.ask_user(q)
                self.question_answers.append((q, ans))

        self.saved_trajectory.question_answers = self.question_answers

        # 3) Clean up user queries and build final self.task
        if not self.stop_event.is_set():
            qclean_call = await call_unified_question_cleaner(self.task, self.question_answers)
            if qclean_call.parsed_output:
                self.task = qclean_call.parsed_output

            context_call = await call_unified_context_cleaner(self.task, self.task_notes, self.context_info)
            if context_call.parsed_output:
                self.task_notes = context_call.parsed_output

        # 4) Action loop
        while not self.stop_event.is_set():
            try:
                self.curr_save_node = SavedTrajectoryNode()

                # a) Call chain-of-thought to determine an action
                action_out_call = await self.action_call(provider="cerebras", model="llama-3.3-70b")
                if action_out_call.parsed_output is None:
                    self.failed_count += 1
                    break

                # b) Action is typically a tuple or dict. For example: (Action.Type, "some reason")
                action_out = action_out_call.parsed_output
                self.curr_save_node.ad_call = action_out_call

                # c) If the action is empty or None, break
                if not action_out:
                    break

                chosen_action_type, reason_for_action = action_out

                # d) Handle special or normal actions
                if chosen_action_type == Action.Type.STOP:  # TODO, different action typing for APIs, ignore for now
                    await self.output_queue.put(('exit_message', "Agent has stopped."))
                    self.stop()

                elif chosen_action_type == Action.Type.REQUEST_USER_INPUT:
                    # The agent wants the user to provide more info
                    inter_call = await call_intermediate_questions_agent(
                        self.task, "", reason_for_action, self.task_notes
                    )
                    inter_questions = inter_call.parsed_output or []
                    results = []
                    for qq in inter_questions:
                        if self.stop_event.is_set():
                            break
                        resp = await self.ask_user(qq)
                        results += f"Q: {qq}\nA: {resp}\n"

                    self.task_notes = self.task_notes # TODO integrate QA into task_notes using a LLM?
                    
                    new_memory = APILinearMemory() # TODO, fill out some logic to record what was requested and returned
                    
                    self.action_mem.append(new_memory) # TODO, integrate fact that questions were asked

                else:
                    # e) Perform a generic API action
                    success = await self.perform_api_action(chosen_action_type, reason_for_action)
                    if not success:
                        self.failed_count += 1
                        if self.failed_count > self.retry_cap:
                            self.stop()
                    else:
                        self.failed_count = 0
                        new_memory = APILinearMemory()  # TODO fill to understand
                        self.action_mem.append(new_memory)  # TODO, integrate the call requested and received



                # g) Save your step
                self.saved_trajectory.add_node(copy.deepcopy(self.curr_save_node))

                gc.collect()

            except Exception as e:
                print(f"Agent encountered exception: {e}")
            finally:
                # If a stop is triggered, do final cleanup
                if self.stop_event.is_set():
                    await self.cleanup()
                else:
                    self.failed_count += 1
                    if self.failed_count > self.retry_cap:
                        self.stop()

    async def perform_api_action(self, action_type, reason_for_action):
        """
        Actually perform the action on your chosen API (Gmail, Calendar, etc.).
        Return True on success, False on failure.
        """
        print(f"Performing API action: {action_type} | Reason: {reason_for_action}")
        # Insert real API logic here
        return True

    async def cleanup(self):
        """Cleanup any resources if needed."""
        gc.collect()
        self.cleaned_up.set()

    def stop(self):
        """Stop execution and save the trajectory to disk."""
        now = datetime.datetime.now()
        filename = f"{self.saved_trajectory.user_input_task}_{now.strftime('%Y%m%d_%H%M')}.pkl"
        directory = 'saved_trajectories'
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, filename), 'wb') as f:
            pickle.dump(self.saved_trajectory, f)
        self.stop_event.set()
