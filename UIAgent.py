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
from inferenceagent import (
    call_action_agent,
    call_unified_task_clarifier,
    call_reflect_agent,
    call_memory_agent,
    call_task_separator,
    call_task_clarifier,
    call_input_agent,
    call_unified_question_cleaner,
    call_check_load_agent_text,
    call_check_load_agent_screenshot
)


class Agent:
    def __init__(self, fast_mode=False, retry_cap=2):
        self.stop_event = asyncio.Event()  # Use asyncio.Event for async compatibility
        self.cleaned_up = asyncio.Event()
        self.playwright_lock = asyncio.Lock()
        self.fast_mode = fast_mode
        self.retry_cap = retry_cap
        # self.reset() UI resets agent, delete agent after done
        self.initialize_index()

        # def reset(self):
        self.scraper_state_file = 'dominos/scraper_state.pkl'
        self.url_state_manager = load_scraper_state(self.scraper_state_file)
        self.task = None
        self.action_mem = []
        self.world_mem = ""
        self.questions = []
        self.question_answers = []
        self.hidden_inputs = [
            HiddenInput('first_name', "User's first name", "James"),
            HiddenInput('last_name', "User's last name", "Chen"),
            HiddenInput('email', "User's email address", "example@gmail.com"),
            HiddenInput('phone_number', "User's phone number", "4121234567")
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
        self.failed_count = 0
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

    async def formulate_questions(self):
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

        # Await the asynchronous call_task_separator
        agent_call = await call_task_separator(self.task)
        self.interesting_items = agent_call.parsed_output if agent_call.parsed_output else []

        self.item_context_pairs = "\n\n".join([
            "Item: " + item + "\n" + "Context: " + "".join(
                [node.get_content() for node in autoregressive_retrieve(self.index, item, top_k)]
            ) for item in self.interesting_items
        ])
        print("Item context pairs\n", self.item_context_pairs)

        self.saved_trajectory.important_info = self.item_context_pairs

        # Read questions.txt asynchronously
        def read_questions():
            with open('data/questions.txt', 'r') as f:
                return f.read()

        self.question_context = await asyncio.to_thread(read_questions)
        print("Question Context\n", self.question_context)

        # Await the asynchronous call_unified_task_clarifier
        agent_call = await call_unified_task_clarifier(self.task, self.question_context)
        self.questions = agent_call.parsed_output if agent_call.parsed_output else []

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

    async def check_if_loaded_screenshot(self):
        async with self.playwright_lock:
            if self.page:
                screenshot = await self.page.screenshot(full_page=False)
                base64_screenshot = base64.b64encode(screenshot).decode('utf-8')
                data_url = f"data:image/png;base64,{base64_screenshot}"
                await call_check_load_agent_screenshot(data_url)

    async def check_if_loaded_text(self):
        async with self.playwright_lock:
            ax_nodes = await get_ax_tree_no_extras(self.cdp_session)
            cleaned = AxObservation(ax_nodes, self.page.url, processed = False)
            is_loaded = await call_check_load_agent_text(cleaned)
            return is_loaded

    async def wait_for_network_idle(self, idle_time=0.2, timeout=1.0):
        """
        Wait until there are no network requests for `idle_time` seconds,
        but no longer than `timeout` seconds in total.

        Args:
            idle_time (float): Seconds of no network activity to consider idle.
            timeout (float): Maximum seconds to wait.

        Raises:
            asyncio.TimeoutError: If the network does not become idle within `timeout`.
        """
        active_requests = set()
        idle_event = asyncio.Event()

        async def set_idle():
            await asyncio.sleep(idle_time)
            if not active_requests:
                idle_event.set()

        def on_request(request):
            active_requests.add(request)
            idle_event.clear()

        def on_request_finished(request):
            active_requests.discard(request)
            if not active_requests:
                asyncio.create_task(set_idle())

        def on_request_failed(request):
            active_requests.discard(request)
            if not active_requests:
                asyncio.create_task(set_idle())

        # Attach event listeners
        self.page.on("request", on_request)
        self.page.on("requestfinished", on_request_finished)
        self.page.on("requestfailed", on_request_failed)

        try:
            # Initial check: if no active requests, start idle timer
            if not active_requests:
                asyncio.create_task(set_idle())

            # Wait for idle_event or timeout
            await asyncio.wait_for(idle_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"Timeout: Network did not become idle within {timeout} seconds.")
        finally:
            # Remove event listeners to prevent memory leaks
            self.page.off("request", on_request)
            self.page.off("requestfinished", on_request_finished)
            self.page.off("requestfailed", on_request_failed)

    async def loop_until_loaded(self, wait_time=6):
        # await asyncio.sleep(1)
        start_time = time.time()
        try:
            # await self.page.wait_for_load_state('networkidle', timeout=1000)
            await self.wait_for_network_idle(idle_time=0.2, timeout=1)
        except:
            pass
        is_loaded = False
        while time.time() - start_time <= wait_time // 2:
            is_loaded = await self.check_if_loaded_text()
            if is_loaded:
                break
            else:
                await asyncio.sleep(0.5)
        if not is_loaded:
            await asyncio.sleep(wait_time // 2)

    async def run(self):
        await self.launch_browser()
        try:
            await self.capture_and_send_screenshot()
            if not self.stop_event.is_set():
                if self.task is None:
                    self.task = await self.ask_user("What do you want done on dominos?")
                    self.saved_trajectory.user_input_task = self.task

            if not self.stop_event.is_set():
                await self.formulate_questions()
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
                agent_call = await call_unified_question_cleaner(self.task, self.question_answers)
                if agent_call.parsed_output:
                    self.task = agent_call.parsed_output
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

                        input_all_action = Action(Action.Type.INPUT_GIVEN_INTENT, None, None)
                        input_all_action.set_special_effect(
                            'Call an agent to fill in all inputs on the page given some intent. {The intent is action_reason you return in choose}')
                        input_all_indefinite = IndefiniteAction([Action.Type.INPUT_GIVEN_INTENT], input_all_action,
                                                                None,
                                                                IndefiniteAction.Location.SPECIAL)

                        special_actions = [stop_indefinite, input_all_indefinite]

                        curr_inf_tree = InferenceAxtree(matched_inference_state, special_actions=special_actions,
                                                        use_scrape=True)
                        if self.stop_event.is_set():
                            break

                        if str(old_inf_tree) != '':  # MAKE THIS LESS BAD
                            reflect_response_call = await call_reflect_agent(
                                reason_for_action,
                                str(old_inf_tree.get_tree_with_specific_action_effect(reflect_action_indices)),
                                # reflect_action_indices used to be chosen_action_index
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

                        # old_inf_tree = curr_inf_tree  NOW SET LATER, WE DON'T SET THIS IF CUR_INF_TREE IS BROKEN OR SOME ACTIONS BREAK
                        if self.stop_event.is_set():
                            break

                        start = time.time()
                        # Check stop_event after API call
                        if self.stop_event.is_set():
                            break

                        action_out_call = await call_action_agent(
                            self.task, curr_inf_tree,
                            self.action_mem, self.item_context_pairs, provider="anthropic"
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
                        reflect_action_indices = [chosen_action_index]
                        reason_for_action = reason_for_action.encode('utf-8').decode('unicode_escape')
                        print(f'reason_for_action: {reason_for_action}')
                        await self.output_queue.put(('only_out', reason_for_action))

                        chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                        chosen_action = chosen_indefinite.action

                        if chosen_action is not None and chosen_action.html is not None and (
                                'payment-order-now' in chosen_action.html or 'Place Your Order' in chosen_action.html):
                            await self.output_queue.put(
                                ('exit_message', "Stopping agent to prevent actually buying a Pizza"))
                            self.stop()
                        elif chosen_indefinite.location != IndefiniteAction.Location.SPECIAL and "pages/order/payment" in self.page.url:  # may be a bad check
                            await self.output_queue.put(
                                ('exit_message', "Stopping agent to prevent actually buying a Pizza"))
                            self.stop()

                        # Check stop_event after API call
                        if self.stop_event.is_set():
                            break

                        action_failed = False

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
                                action_failed = True
                                # self.stop()
                        else:
                            if chosen_action.action_type == Action.Type.STOP:
                                # self.failed_count += 1
                                # if self.failed_count > self.retry_cap:
                                #     self.stop()
                                # else:
                                #     self.action_mem = self.action_mem[:-1]  # pop may break
                                action_failed = True  # currently we assume the agent stopping itself is an error, may want a special load action????

                            elif chosen_action.action_type == Action.Type.INPUT_GIVEN_INTENT:
                                desired = await call_input_agent(
                                    self.task, reason_for_action,
                                    curr_inf_tree.get_input_tree(), self.context_info,
                                    self.hidden_inputs
                                )
                                if desired.parsed_output is None:
                                    raise Exception
                                for (chosen_action_index, input_string) in desired.parsed_output:
                                    if self.stop_event.is_set():
                                        break
                                    reflect_action_indices.append(chosen_action_index)
                                    unhidden_input_string = replace_hidden_inputs(input_string, self.hidden_inputs)
                                    chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                                    chosen_action = chosen_indefinite.action
                                    chosen_element, chosen_xpath, type_list = await get_chosen_element(
                                        self.page,
                                        chosen_indefinite
                                    )
                                    chosen_action.set_input_string(unhidden_input_string)
                                    if self.stop_event.is_set():
                                        break
                                    success = await do_action_flow(
                                        self.page, chosen_action, chosen_element, chosen_xpath,
                                        type_list
                                    )
                                    if not success:
                                        action_failed = True  # note that AD still sees curr ax tree and input agent is independent, so shouldn't break
                                        # self.stop()

                                    if self.stop_event.is_set():
                                        break

                        if action_failed:
                            self.action_mem = self.action_mem[:-1]
                            self.failed_count += 1
                            if self.failed_count > self.retry_cap:
                                self.stop()
                        else:
                            self.failed_count = 0
                            old_inf_tree = curr_inf_tree

                    else:
                        print("No matched state, why?")

                    self.saved_trajectory.add_node(copy.deepcopy(self.curr_save_node))

                if self.stop_event.is_set():
                    break
                gc.collect()

                if self.fast_mode:
                    start_time = time.time()
                    wait_time = 6
                    timeout_wait = wait_time + 1
                    try:
                        await asyncio.wait_for(self.loop_until_loaded(wait_time=wait_time), timeout=timeout_wait)
                    except asyncio.TimeoutError:
                        print("Timeout reached while waiting for text to load.")

                    print(f"Lapsed time: {time.time() - start_time}")
                else:
                    await asyncio.sleep(6)
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
                await self.output_queue.put(('exit_message', "Agent crashed, please reset."))
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
