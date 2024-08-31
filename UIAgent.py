import copy
import queue

from utils.element_utils.element_similarity import element_similarity
from pathlib import Path
import os
from bs4 import BeautifulSoup
import numpy as np
from PIL import Image, ImageDraw
import cv2
import copy as cp
import pickle
import re
from models import PageObservation
from inferenceagent import *
import time
from scrape7 import setup_context
from utils import *
from utils.inference_data import *
from utils.inference_helpers import *
from llama_index.core.schema import TextNode
from llama_index.core import VectorStoreIndex
from utils.element_utils.element_similarity import element_similarity
from typing import List
from queue import Queue
import base64
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from playwright.async_api import async_playwright
import threading
import asyncio

class Agent:
    def __init__(self):
        self.stop_event = threading.Event()
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
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.stop_event.clear()
        self.playwright = None
        self.browser = None
        self.browser_context = None
        self.page = None
        self.cdp_session = None

    def ask_user(self, question):
        self.output_queue.put(('question', question))
        while not self.stop_event.is_set():
            try:
                return self.input_queue.get(timeout=0.1)
            except queue.Empty:
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
        self.interesting_items = call_task_separator(self.task)
        self.item_context_pairs = "\n\n".join(["Item: " + item + "\n" + "Context: " + "".join(
            [node.get_content() for node in autoregressive_retrieve(self.index, item, top_k)]) for item in
                                               self.interesting_items])
        print(self.item_context_pairs)
        self.questions = call_unified_task_clarifier(self.task, self.item_context_pairs)

    async def launch_browser(self):
        async with self.playwright_lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            if self.browser is None:
                self.browser = await self.playwright.chromium.launch(headless=False)
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

    async def capture_and_send_screenshot(self):
        async with self.playwright_lock:
            if self.page:
                screenshot = await self.page.screenshot(full_page=False)
                base64_screenshot = base64.b64encode(screenshot).decode('utf-8')
                self.output_queue.put(('screenshot', base64_screenshot))

    async def run(self):
        await self.launch_browser()
        try:
            await self.capture_and_send_screenshot()
            # Process task and questions once
            if self.task is None:
                self.task = self.ask_user("What do you want done on dominos?")

            self.formulate_questions()

            for question in self.questions:
                if self.stop_event.is_set():
                    break
                answer = self.ask_user(question)
                self.question_answers.append((question, answer))

            if not self.stop_event.is_set():
                self.task = call_unified_question_cleaner(self.task, self.question_answers)

            base_state = None
            old_inf_tree = ''

            # Main action loop
            while not self.stop_event.is_set():
                await self.capture_and_send_screenshot()

                async with self.playwright_lock:
                    curr_page_state = await get_page_state(self.page, self.cdp_session)
                    if base_state is None:
                        base_state = curr_page_state

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

                        if str(old_inf_tree) != '':
                            mem_response = call_reflect_agent(chosen_action_index, reason_for_action, str(old_inf_tree),
                                                              str(curr_inf_tree), self.task)
                            if mem_response is None:
                                raise Exception
                            old_web_page_purpose, object_and_effect = mem_response[0], mem_response[1]
                            new_memory = LinearMemory(object_details=old_web_page_purpose,
                                                      location_details=object_and_effect)
                            self.action_mem.append(new_memory)

                        old_inf_tree = curr_inf_tree

                        at_new_state = is_different_page(base_state, curr_page_state)
                        if at_new_state:
                            base_state = curr_page_state
                            self.world_mem = call_memory_agent(self.task, self.action_mem,
                                                               self.world_mem)
                            self.action_mem = []

                        start = time.time()
                        action_out = call_action_agent(self.task, curr_inf_tree, self.world_mem,
                                                       self.action_mem, self.item_context_pairs)
                        print("Action took", time.time() - start)

                        if action_out is None:
                            raise Exception

                        chosen_action_index, reason_for_action = action_out
                        reason_for_action = reason_for_action.encode('utf-8').decode('unicode_escape')
                        print(f'reason_for_action: {reason_for_action}')
                        self.output_queue.put(('only_out', reason_for_action))

                        chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                        chosen_action = chosen_indefinite.action

                        if chosen_indefinite.location != IndefiniteAction.Location.SPECIAL:
                            chosen_element, chosen_xpath, type_list = await get_chosen_element(self.page,
                                                                                         chosen_indefinite)
                            success = await do_action_flow(self.page, chosen_action, chosen_element, chosen_xpath,
                                                     type_list)
                            if not success:
                                print(f"This action was broken: {chosen_action}")
                                self.stop_event.set()
                        else:
                            if chosen_action.action_type == Action.Type.STOP:
                                self.stop_event.set()
                            elif chosen_action.action_type == Action.Type.INPUT_GIVEN_INTENT:
                                desired = call_input_agent(self.task, reason_for_action,
                                                           curr_inf_tree.get_input_tree(), self.context_info,
                                                           self.hidden_inputs)
                                for (chosen_action_index, input_string) in desired:
                                    unhidden_input_string = replace_hidden_inputs(input_string, self.hidden_inputs)
                                    chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                                    chosen_action = chosen_indefinite.action
                                    chosen_element, chosen_xpath, type_list = await get_chosen_element(self.page,
                                                                                                 chosen_indefinite)
                                    chosen_action.set_input_string(unhidden_input_string)
                                    success = await do_action_flow(self.page, chosen_action, chosen_element, chosen_xpath,
                                                             type_list)
                    else:
                        print("No matched state, why?")

                    time.sleep(5)
        finally:
            print("CLEANING")
            await self.cleanup_browser()
            print("FINISHED CLEANING")
            print("DONE!")

    def stop(self):
        print("Stop method called")
        self.stop_event.set()