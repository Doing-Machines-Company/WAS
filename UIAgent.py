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
from playwright.sync_api import sync_playwright
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


class Agent:
    def __init__(self):
        self.scraper_state_file = 'dominos/scraper_state.pkl'
        self.url_state_manager = load_scraper_state(self.scraper_state_file)
        self.task = None
        self.keep_running = True
        self.action_mem = []
        self.world_mem = ""
        self.questions = []
        self.question_answers = []
        self.hidden_inputs = [
            HiddenInput('first_name', "User's first name", "James"),
            HiddenInput('last_name', "User's last name", "Chen")
        ]
        self.browser = None
        self.browser_context = None
        self.page = None
        self.cdpSession = None
        self.index = None
        self.retriever = None
        self.clarifications = None
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.at_new_state = False
        self.ws_endpoint = None
        self.playwright = None

    def ask_user(self, question):
        self.output_queue.put(('question', question))
        return self.input_queue.get()  # This will block until input is received

    def initialize_index(self):
        print("Creating...")
        start = time.time()
        with open('./data/factsNEW.txt', 'r') as f:
            document = f.read()
        nodes = [TextNode(text=chunk, id_=i) for (i, chunk) in enumerate(document.split('***'))]
        # print(nodes)
        # print("CHECKKK")
        self.index = VectorStoreIndex(nodes)
        self.retriever = self.index.as_retriever(vector_store_query_mode="mmr",
                                                 vector_store_kwargs={"mmr_threshold": 1})
        print("took", time.time() - start)
        def autoregressive_retrieve(index, task, k=2):
            new_task = task 
            nodes = []
            for i in range(k):
                retriever = index.as_retriever(similarity_top_k = i+1)
                new_node = retriever.retrieve(new_task)[-1]
                new_task += new_node.get_content()
                nodes.append(new_node)
            return nodes
        top_k = 2
        self.context_info = "\n".join([node.get_content() for node in self.retriever.retrieve(self.task)])
        self.interesting_items = call_task_separator(self.task)
        self.item_context_pairs = "\n\n".join(["Item: " + item + "\n" + "Context: " + "".join(
            [node.get_content() for node in autoregressive_retrieve(self.index, item, top_k)]) for item in self.interesting_items])

        self.questions = call_unified_task_clarifier(self.task, self.item_context_pairs)

    def launch_browser(self):
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        if self.browser is None:
            self.browser = self.playwright.chromium.launch(headless=False)
        if self.browser_context is None or self.page is None or self.cdpSession is None:
            self.browser_context, self.page, self.cdpSession, _ = setup_context(self.browser, None)

    def capture_and_send_screenshot(self):
        screenshot = self.page.screenshot(full_page=False)
        base64_screenshot = base64.b64encode(screenshot).decode('utf-8')
        self.output_queue.put(('screenshot', base64_screenshot))

    def run(self):
        self.launch_browser()
        self.capture_and_send_screenshot()
        self.task = self.ask_user("What do you want done on dominos?")
        self.initialize_index()

        for question in self.questions:
            answer = self.ask_user(question)
            self.question_answers.append((question, answer))

        self.clarifications = call_unified_question_cleaner(self.task, self.question_answers)
        time.sleep(5)
        base_state = get_page_state(self.page, self.cdpSession)
        old_inf_tree = ''

        while self.keep_running:

            self.capture_and_send_screenshot()
            curr_page_state = get_page_state(self.page, self.cdpSession)
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
                                                      str(curr_inf_tree), self.task, self.clarifications)
                    if mem_response is None:
                        raise Exception
                    old_web_page_purpose, object_and_effect = mem_response[0], mem_response[1]
                    new_memory = LinearMemory(object_details=old_web_page_purpose, location_details=object_and_effect)
                    self.action_mem.append(new_memory)

                old_inf_tree = curr_inf_tree

                self.at_new_state = is_different_page(base_state, curr_page_state)
                if self.at_new_state:
                    self.at_new_state = False
                    base_state = curr_page_state
                    self.world_mem = call_memory_agent(self.task, self.clarifications, self.action_mem, self.world_mem)
                    self.action_mem = []

                action_out = call_action_agent(self.task, self.clarifications, curr_inf_tree, self.world_mem,
                                               self.action_mem, self.item_context_pairs)

                if action_out is None:
                    raise Exception

                chosen_action_index, reason_for_action = action_out

                self.output_queue.put(('only_out', reason_for_action))

                chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                chosen_action = chosen_indefinite.action

                if chosen_indefinite.location != IndefiniteAction.Location.SPECIAL:
                    chosen_element, chosen_xpath, type_list = get_chosen_element(self.page, chosen_indefinite)
                    success = do_action_flow(self.page, chosen_action, chosen_element, chosen_xpath, type_list)

                    if not success:
                        print(f"This action was broken: {chosen_action}")
                        self.keep_running = False

                else:

                    if chosen_action.action_type == Action.Type.STOP:
                        self.keep_running = False
                        break

                    elif chosen_action.action_type == Action.Type.INPUT_GIVEN_INTENT:
                        desired = call_input_agent(self.task, reason_for_action, self.clarifications,
                                                   curr_inf_tree.get_input_tree(), self.context_info,
                                                   self.hidden_inputs)
                        for (chosen_action_index, input_string) in desired:
                            unhidden_input_string = replace_hidden_inputs(input_string, self.hidden_inputs)
                            chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)
                            chosen_action = chosen_indefinite.action
                            chosen_element, chosen_xpath, type_list = get_chosen_element(self.page, chosen_indefinite)
                            chosen_action.set_input_string(unhidden_input_string)
                            success = do_action_flow(self.page, chosen_action, chosen_element, chosen_xpath, type_list)

            else:
                print("No matched state, why?")

            time.sleep(5)  # Adjust as needed
            self.capture_and_send_screenshot()

    def stop(self):
        self.keep_running = False
        self.cdpSession.detach()
        self.page.close()
        self.browser_context.close()
        self.browser.close()
