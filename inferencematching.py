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
from utils.inference_data import *  # here are the dataclasses for this script
from utils.inference_helpers import *  # here are the functions for this script
from llama_index.core.schema import TextNode
from llama_index.core import VectorStoreIndex
from utils.element_utils.element_similarity import element_similarity
from typing import List




scraper_state_file = 'dominos/scraper_state.pkl'
url_state_manager = load_scraper_state(scraper_state_file)
task = 'buy me a veggie sandwich, a hawaiian pizza, and a coke'

keep_running = True
action_mem = []
world_mem = ""
print("Creating...")
start = time.time()
with open('./data/factsNEW.txt', 'r') as f:
    document = f.read()
nodes = [TextNode(text = chunk, id_ = i) for (i, chunk) in enumerate(document.split('***'))]
index = VectorStoreIndex(nodes)
retriever = index.as_retriever(vector_store_query_mode="mmr", vector_store_kwargs={"mmr_threshold": 0.8})
print("took", time.time() - start)
# start = time.time()
# context_info = "\n".join([node.get_content() for node in retriever.retrieve(task)])
# print("Retrieving took...", time.time() -start)
# print(context_info)
interesting_items: list[str] = call_task_separator(task)
item_context_pairs = "\n\n".join(["Item: " + item + "\n" + "Context: " + "".join([node.get_content() for node in retriever.retrieve(item)]) for item in interesting_items])
input(item_context_pairs)
questions: list[str] = call_unified_task_clarifier(task, item_context_pairs)
input(questions)
# question_answers = []

# for question in questions:
#     user_answer = input('QUESTION: \n' + question + '\nANSWER: \n')
#     question_answers.append((question, user_answer))

# clarifications = call_unified_question_cleaner(task, question_answers)  # may want this to explicitly include more key words

# hidden_inputs = [HiddenInput('first_name', "User's first name", "James"),
#                  HiddenInput('last_name', "User's last name", "Chen")]


# wait = True
# with sync_playwright() as p:
#     browser = p.chromium.launch(headless=False)
#     context, page, cdpSession, login_success = setup_context(browser, None)
#     page.goto('https://www.dominos.com/')
#     wait_for_load(page)

#     base_state = get_page_state(page, cdpSession)
#     at_new_state = False
#     old_inf_tree = ''

#     while keep_running:
#         trajectory_action_screenshot = None
#         chosen_element = None
#         chosen_xpath = None
#         start = time.time()
#         # print("Fetching page resources: ", time.time() - start)
#         curr_page_state = get_page_state(page, cdpSession)
#         matched_inference_state = match_action_effects(curr_page_state, url_state_manager)
#         # print("Matching actions: ", time.time() - start)
#         if matched_inference_state:




#             stop_action = Action(Action.Type.STOP, None, None)
#             stop_action.set_special_effect('Stop trying to perform user task, use if task is impossible or finished. {Stops and give user control}')
#             stop_indefinite = IndefiniteAction([Action.Type.STOP], stop_action, None, IndefiniteAction.Location.SPECIAL)



#             special_actions = [stop_indefinite]
#             # special_actions = []
#             curr_inf_tree = InferenceAxtree(matched_inference_state, special_actions=special_actions, use_scrape=True)
#             start = time.time()

#             if str(old_inf_tree) != '':
#                 mem_response = call_reflect_agent(chosen_action_index, reason_for_action, str(old_inf_tree), str(curr_inf_tree))
#                 if mem_response is None:
#                     raise Exception
#                 old_web_page_purpose, object_and_effect = mem_response[0], mem_response[1]
#                 new_memory = LinearMemory(object_and_effect, old_web_page_purpose)
#                 action_mem.append(new_memory)

#             old_inf_tree = curr_inf_tree

#             at_new_state = is_different_page(base_state, curr_page_state)
#             if at_new_state:
#                 at_new_state = False  # resets
#                 base_state = curr_page_state
#                 world_mem = call_memory_agent(task, clarifications, action_mem, world_mem)  # perhaps can be even cleaner, less navigation
#                 action_mem = []

#             action_out = call_action_agent(task, clarifications, curr_inf_tree, world_mem, action_mem, context_info)
#             # print("Inference took: ", time.time() - start)
#             # print(f"THIS ONE: {answer}")
#             if action_out is None:
#                 raise Exception

#             chosen_action_index, reason_for_action = action_out

#             chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)  # TODO MAKE SURE YOU GET ACTION TYPE FROM SCRAPE TIME
#             chosen_action = chosen_indefinite.action

#             if chosen_indefinite.location != IndefiniteAction.Location.SPECIAL:
#             # if chosen_indefinite not in special_actions:

#                 chosen_element, chosen_xpath, type_list = get_chosen_element(page, chosen_indefinite)

#                 success = do_action_flow(page, chosen_action, chosen_element, chosen_xpath, type_list)

#                 input("DID ACTION")

#                 if not success:
#                     print(f"This action was broken: {chosen_action}")
#                     keep_running = False


#             else:
#                 type_list = chosen_indefinite.type_list

#                 if wait:
#                     # print(chosen_action)
#                     input("ABOUT TO DO ACTION")

#                 if chosen_action.action_type == Action.Type.STOP:
#                     keep_running = False
#                     input("STOPPING")
#                     break

#                 elif chosen_action.action_type == Action.Type.INPUT_GIVEN_INTENT:
#                     # def call_input_agent(user_task, agent_intent, task_details, input_ax_tree, context):
#                     desired = call_input_agent(task, reason_for_action, clarifications, curr_inf_tree.get_input_tree(), context, hidden_inputs)
#                     # desired is [(int(i), s) for i, s in matches]
#                     print("DESIRED")
#                     print(desired)
#                     for (chosen_action_index, input_string) in desired:
#                         print("TRYING!!!")

#                         unhidden_input_string = replace_hidden_inputs(input_string, hidden_inputs)  # uses regex

#                         chosen_indefinite = curr_inf_tree.get_action_from_index(
#                             chosen_action_index)  # TODO MAKE SURE YOU GET ACTION TYPE FROM SCRAPE TIME
#                         chosen_action = chosen_indefinite.action

#                         chosen_element, chosen_xpath, type_list = get_chosen_element(page, chosen_indefinite)

#                         chosen_action.set_input_string(unhidden_input_string)

#                         success = do_action_flow(page, chosen_action, chosen_element, chosen_xpath, type_list)
#                         # chosen_action.

#                 if wait:
#                     input("DID ACTION")

#             if wait:
#                 do_keep_running = input('want to keep running?')
#                 if do_keep_running != '':
#                     keep_running = False

#             # def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None)
#             # apply_action(page, chosen_action, page.screenshot(), None, None, None)
#         else:
#             print("No matched state, why?")