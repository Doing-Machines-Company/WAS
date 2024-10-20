# UIAgent.py

import copy
import asyncio
import gc
import time
from utils.inference_helpers import *
from llama_index.core.schema import TextNode
from llama_index.core import VectorStoreIndex
import base64
from playwright.async_api import async_playwright
import datetime
import os
import pickle
from utils.inference_data import *
from utils.trajectory_saves import *

class Agent:
    def __init__(self):
        self.stop_event = asyncio.Event()  # Use asyncio.Event for async compatibility
        self.cleaned_up = asyncio.Event()
        self.playwright_lock = asyncio.Lock()
        self.reset()
        self.initialize_index()

    def reset(self):
        self.scraper_state_file = 'dominos/scraper_state.pkl'
        self.url_state_manager = load_scraper_state(self.scraper_state_file)
        self.task = None
        self.action_mem = []
        self.world_mem = ""
        self.questions = []
        self.question_answers = []
        self.hidden_inputs = [
            HiddenInput('first_name', "User's first name", "James"),
            HiddenInput('last_name', "User's last name", "Chen")
        ]
        self.input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()
        self.stop_event.clear()
        self.playwright = None
        self.browser = None
        self.browser_context = None
        self.page = None
        self.cdp_session = None
        self.curr_save_node = None
        self.saved_trajectory = SavedTrajectory()

    async def ask_user(self, question):
        await self.output_queue.put(('question', question))
        while not self.stop_event.is_set():
            try:
                response = await asyncio.wait_for(self.input_queue.get(), timeout=0.1)
                return response
            except asyncio.TimeoutError:
                continue
        raise InterruptedError("Agent stopped")

    def initialize_index(self):
        print("Creating...")
        start = time.time()
        with open('./data/factsNEW.txt', 'r') as f:
            document = f.read()
        nodes = [TextNode(text=chunk, id_=i) for (i, chunk) in enumerate(document.split('***'))]
        self.index = VectorStoreIndex(nodes)
        self.retriever = self.index.as_retriever(vector_store_query_mode="mmr",
                                                 vector_store_kwargs={"mmr_threshold": 1})
        print("took", time.time() - start)

    def formulate_questions(self):
        def autoregressive_retrieve(index, task, k=2):
            new_task = task
            nodes = []
            for i in range(k):
                retriever = index.as_retriever(similarity_top_k=i + 1)
                new_node = retriever.retrieve(new_task)[-1]
                new_task += new_node.get_content()
                nodes.append(new_node)
            return nodes

        top_k = 2
        self.context_info = "\n".join([node.get_content() for node in self.retriever.retrieve(self.task)])
        self.interesting_items = call_task_separator(self.task).parsed_output
        self.item_context_pairs = "\n\n".join([
            "Item: " + item + "\n" + "Context: " + "".join(
                [node.get_content() for node in autoregressive_retrieve(self.index, item, top_k)]
            ) for item in self.interesting_items
        ])
        print("Item context pairs\n", self.item_context_pairs)

        self.saved_trajectory.important_info = self.item_context_pairs

        with open('data/questions.txt', 'r') as f:
            self.question_context = f.read()
        print("Question Context\n", self.question_context)
        self.questions = call_unified_task_clarifier(self.task, self.question_context).parsed_output

    async def launch_browser(self):
        async with self.playwright_lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            if self.browser is None:
                self.browser = await self.playwright.chromium.launch(headless=True)
            if self.browser_context is None or self.page is None or self.cdp_session is None:
                try:
                    self.browser_context, self.page, self.cdp_session, _ = await setup_context(self.browser, None)
                except Exception as e:
                    print(f"Error during setup_context: {e}")
                    await self.cleanup_browser()
                    raise

    async def cleanup_browser(self):
        async with self.playwright_lock:
            try:
                if self.cdp_session:
                    await self.cdp_session.detach()
                if self.page:
                    await self.page.close()
                if self.browser_context:
                    await self.browser_context.close()
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                print(f"Error during browser cleanup: {e}")
            finally:
                self.playwright = None
                self.browser = None
                self.browser_context = None
                self.page = None
                self.cdp_session = None
            gc.collect()
            self.cleaned_up.set()

    async def capture_and_send_screenshot(self, save_node=None):
        async with self.playwright_lock:
            if self.page:
                screenshot = await self.page.screenshot(full_page=False)
                base64_screenshot = base64.b64encode(screenshot).decode('utf-8')
                if save_node is not None:
                    save_node.screenshot = base64_screenshot
                await self.output_queue.put(('screenshot', base64_screenshot))

    async def run(self):
        await self.launch_browser()
        try:
            await self.capture_and_send_screenshot()
            # Process task and questions once
            if not self.stop_event.is_set():
                if self.task is None:
                    self.task = await self.ask_user("What do you want done on dominos?")
                    self.saved_trajectory.user_input_task = self.task

            if not self.stop_event.is_set():
                self.formulate_questions()
                print(self.questions)
                for question in self.questions:
                    if self.stop_event.is_set():
                        break
                    answer = await self.ask_user(question)
                    self.question_answers.append((question, answer))
                    # Check stop_event after each user response
                    if self.stop_event.is_set():
                        break

            self.saved_trajectory.question_answers = self.question_answers

            if not self.stop_event.is_set():
                self.task = call_unified_question_cleaner(self.task, self.question_answers).parsed_output
                self.cleaned_task = self.saved_trajectory.cleaned_task

            base_state = None
            old_inf_tree = ''

            # Main action loop
            while not self.stop_event.is_set():
                self.curr_save_node = SavedTrajectoryNode()
                await self.capture_and_send_screenshot(self.curr_save_node)

                async with self.playwright_lock:
                    curr_page_state = await get_page_state(self.page, self.cdp_session)
                    if base_state is None:
                        base_state = curr_page_state
                    self.curr_save_node.url = self.page.url

                    matched_inference_state = match_action_effects(curr_page_state, self.url_state_manager)

                    if matched_inference_state:
                        stop_action = Action(Action.Type.STOP, None, None)
                        stop_action.set_special_effect(
                            'Stop trying to perform user task, use if task is impossible or finished. {Stops and give user control}')
                        stop_indefinite = IndefiniteAction([Action.Type.STOP], stop_action, None,
                                                           IndefiniteAction.Location.SPECIAL)
                        special_actions = [stop_indefinite]

                        curr_inf_tree = InferenceAxtree(matched_inference_state, special_actions=special_actions,
                                                        use_scrape=True)
                        if self.stop_event.is_set():
                            break

                        if str(old_inf_tree) != '':
                            reflect_response_call = call_reflect_agent(
                                chosen_action_index, reason_for_action,
                                str(old_inf_tree.get_tree_with_specific_action_effect(chosen_action_index)),
                                curr_inf_tree.get_raw_tree(), self.task
                            )
                            self.curr_save_node.reflect_call = copy.deepcopy(reflect_response_call)
                            mem_response = reflect_response_call.parsed_output
                            if mem_response is None:
                                raise Exception
                            old_web_page_purpose, object_and_effect = mem_response[0], mem_response[1]
                            new_memory = LinearMemory(object_details=old_web_page_purpose,
                                                      location_details=object_and_effect)
                            self.action_mem.append(new_memory)

                        old_inf_tree = curr_inf_tree
                        if self.stop_event.is_set():
                            break

                        at_new_state = is_different_page(base_state, curr_page_state)
                        if at_new_state:
                            base_state = curr_page_state
                            world_mem_call = call_memory_agent(self.task, self.action_mem,
                                                               self.world_mem)
                            self.curr_save_node.world_mem_call = copy.deepcopy(world_mem_call)
                            self.world_mem = world_mem_call.parsed_output
                            self.action_mem = []

                        start = time.time()
                        # Check stop_event after API call
                        if self.stop_event.is_set():
                            break

                        action_out_call = call_action_agent(
                            self.task, curr_inf_tree, self.world_mem,
                            self.action_mem, self.item_context_pairs, provider="openai"
                        )
                        # Check stop_event after API call
                        if self.stop_event.is_set():
                            break
                        self.curr_save_node.ad_call = copy.deepcopy(action_out_call)
                        action_out = action_out_call.parsed_output
                        print("Action took", time.time() - start)

                        if action_out is None:
                            raise Exception

                        chosen_action_index, reason_for_action = action_out
                        reason_for_action = reason_for_action.encode('utf-8').decode('unicode_escape')
                        print(f'reason_for_action: {reason_for_action}')
                        await self.output_queue.put(('only_out', reason_for_action))

                        chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                        chosen_action = chosen_indefinite.action

                        # Check stop_event after API call
                        if self.stop_event.is_set():
                            break

                        if chosen_indefinite.location != IndefiniteAction.Location.SPECIAL:
                            chosen_element, chosen_xpath, type_list = await get_chosen_element(
                                self.page,
                                chosen_indefinite
                            )
                            success = await do_action_flow(
                                self.page, chosen_action, chosen_element, chosen_xpath,
                                type_list
                            )
                            if not success:
                                print(f"This action was broken: {chosen_action}")
                                self.stop()
                        else:
                            if chosen_action.action_type == Action.Type.STOP:
                                self.stop()
                            elif chosen_action.action_type == Action.Type.INPUT_GIVEN_INTENT:
                                desired = call_input_agent(
                                    self.task, reason_for_action,
                                    curr_inf_tree.get_input_tree(), self.context_info,
                                    self.hidden_inputs
                                ).parsed_output
                                for (chosen_action_index, input_string) in desired:
                                    unhidden_input_string = replace_hidden_inputs(input_string, self.hidden_inputs)
                                    chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                                    chosen_action = chosen_indefinite.action
                                    chosen_element, chosen_xpath, type_list = await get_chosen_element(
                                        self.page,
                                        chosen_indefinite
                                    )
                                    chosen_action.set_input_string(unhidden_input_string)
                                    success = await do_action_flow(
                                        self.page, chosen_action, chosen_element, chosen_xpath,
                                        type_list
                                    )
                                    if not success:
                                        self.stop()

                    else:
                        print("No matched state, why?")

                    self.saved_trajectory.add_node(copy.deepcopy(self.curr_save_node))

                if self.stop_event.is_set():
                    break
                gc.collect()
                await asyncio.sleep(5)

                # Check stop_event after sleep
                if self.stop_event.is_set():
                    break
        except Exception as e:
            print(f"Agent encountered an exception: {e}")
        finally:
            if self.stop_event.is_set():  # only set in self.stop()
                print("Stop event detected. Initiating cleanup...")
                print("CLEANING")
                await self.cleanup_browser()
                print("FINISHED CLEANING")
                print("DONE!")
            else:
                await self.output_queue.put(('only_out', "Agent crashed, please reset."))
                self.stop()
                await self.cleanup_browser()

    def stop(self):
        print("Stop method called")
        # Get the current date and time
        now = datetime.datetime.now()
        filename = f"{self.saved_trajectory.user_input_task}_{now.strftime('%Y%m%d_%H%M')}.pkl"

        save_directory = 'saved_trajectories'
        if not os.path.exists(save_directory):
            os.makedirs(save_directory)

        full_path = os.path.join(save_directory, filename)
        with open(full_path, 'wb') as file:
            pickle.dump(self.saved_trajectory, file)
        self.stop_event.set()
