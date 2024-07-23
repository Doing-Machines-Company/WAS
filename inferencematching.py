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
from llama_index.core.schema import TextNode
from llama_index.core import VectorStoreIndex
from utils.element_utils.element_similarity import element_similarity

from typing import List
@dataclass
class LinearMemory:
    object_details: str
    location_details: str

    def __repr__(self):
        return f"({self.object_details}, {self.location_details})"
        # return f"{self.action_effect} + {self.location_details} + {self.object_details}"

def load_scraper_state(file_path: str):
    with open(file_path, 'rb') as f:
        return pickle.load(f)

def match_tree_to_scrape(page, equiv_class_set):
    curr_page_html = page.content()
    equiv_class_set.get_class(page.url, curr_page_html)

def match_action_effects(curr_page_state: PageState, url_state_manager: URLStateManager) -> InferencePageState | None:  # Needless amounts of unrolling and rerolling
    found_state = url_state_manager.get_state(curr_page_state)
    if found_state:
        curr_page_actions = [action for action in curr_page_state.actions]  # (typeList, action)
        new_action_list = found_state.match_actions(curr_page_actions)
        inference_page_state = InferencePageState(curr_page_state.url, curr_page_state.ax_nodes, curr_page_state.html, found_state, new_action_list)
        return inference_page_state

    else:
        print("NOTHING FOUND")
        return None

'''

@dataclass
class IndefiniteAction:
    type_list: list[Action.Type]
    action: Action | None
    ax_node_index: int
    
    



'''
scraper_state_file = 'dominos/scraper_state.pkl'
url_state_manager = load_scraper_state(scraper_state_file)
task = 'i want 2 veggie sandwiches and 1 salad'
keep_running = True
action_mem = []
world_mem = ""
print("Creating...")
start = time.time()
with open('./data/facts.txt', 'r') as f:
    document = f.read()
nodes = [TextNode(text = chunk, id_ = i) for (i, chunk) in enumerate(document.split('***'))]
index = VectorStoreIndex(nodes)
retriever = index.as_retriever()
# print("took", time.time() - start)
start = time.time()
context_info = "\n".join([node.get_content() for node in retriever.retrieve(task)])
# print("Retrieving took...", time.time() -start)
# print(context_info)

def is_different_page(base_state, new_state):  # TODO, put this in some util after finalization
    # TODO JACCARD SIM THESE
    if len(base_state.actions) == 0 or len(new_state.actions) == 0:
        return False

    similar_count = 0
    for base_action in base_state.actions:
        base_html = base_action.action.html
        found = False
        for new_action in new_state.actions:
            if found:
                break
            else:
                new_html = new_action.action.html
                if element_similarity(base_html, new_html) >= 0.9:
                    similar_count += 1
                    found = True

    score = similar_count / (len(base_state.actions) + len(new_state.actions) - similar_count)
    if score >= 0.9:  # this was arbitrary, not enough empirical data
        return False
    return True




wait = True
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context, page, cdpSession, login_success = setup_context(browser, None)
    page.goto('https://www.dominos.com/')
    wait_for_load(page)

    base_state = get_page_state(page, cdpSession)
    at_new_state = False
    old_inf_tree = ''

    while keep_running:
        trajectory_action_screenshot = None
        chosen_element = None
        chosen_xpath = None
        start = time.time()
        # print("Fetching page resources: ", time.time() - start)
        start = time.time()
        curr_page_state = get_page_state(page, cdpSession)
        matched_inference_state = match_action_effects(curr_page_state, url_state_manager)
        # print("Matching actions: ", time.time() - start)
        if matched_inference_state:




            stop_action = Action(Action.Type.STOP, None, None)
            stop_action.set_special_effect('Stop trying to perform user task and finish')
            stop_indefinite = IndefiniteAction([Action.Type.STOP], stop_action, None, IndefiniteAction.Location.SPECIAL)
            # special_actions = [stop_indefinite]
            special_actions = []
            curr_inf_tree = InferenceAxtree(matched_inference_state, special_actions=special_actions, use_scrape=True)
            start = time.time()

            if str(old_inf_tree) != '':
                mem_response = call_reflect_agent(chosen_action_index, str(old_inf_tree), str(curr_inf_tree))
                if mem_response is None:
                    raise Exception
                old_web_page_purpose, object_and_effect = mem_response[0], mem_response[1]
                new_memory = LinearMemory(object_and_effect, old_web_page_purpose)
                action_mem.append(new_memory)

            old_inf_tree = curr_inf_tree

            at_new_state = is_different_page(base_state, curr_page_state)
            if at_new_state:
                at_new_state = False  # resets
                base_state = curr_page_state
                world_mem = call_memory_agent(task, action_mem, world_mem)
                action_mem = []

            chosen_action_index = call_action_agent(task, curr_inf_tree, world_mem, action_mem, context_info)
            # print("Inference took: ", time.time() - start)
            # print(f"THIS ONE: {answer}")
            if chosen_action_index is None:
                raise Exception

            chosen_indefinite = curr_inf_tree.get_action_from_index(chosen_action_index)  # TODO MAKE SURE YOU GET ACTION TYPE FROM SCRAPE TIME
            chosen_action = chosen_indefinite.action

            if chosen_indefinite not in special_actions:
                if chosen_action.action_type is not None:
                    type_list = [chosen_action.action_type]
                    for item in chosen_indefinite.type_list:
                        if item not in type_list:
                            type_list.append(item)
                else:
                    type_list = chosen_indefinite.type_list


                chosen_element = get_element(page, chosen_action.xpath)
                # assert(traj_action.friendly_xpath != None)

                chosen_xpath = chosen_action.xpath
                if not chosen_element or chosen_element.count() < 1 or chosen_element.evaluate(
                        "element => element.outerHTML") != chosen_action.html:  # perhaps do a stripped check
                    print('First attempt in traj failed')
                    chosen_element = get_element(page, chosen_action.friendly_xpath)
                    chosen_xpath = chosen_action.friendly_xpath
                    if not chosen_element or chosen_element.count() < 1 or chosen_element.evaluate(
                            "element => element.outerHTML") != chosen_action.html:
                        print('Second attempt in traj failed')
                        # now we try getting stuff at rune time
                        potentially_better_chosen_xpath = get_xpath_by_outer_html(page, chosen_action.html)
                        potentially_better_friendly_chosen_xpath = make_xpath_friendly(potentially_better_chosen_xpath)
                        chosen_element = get_element(page, potentially_better_friendly_chosen_xpath)
                        chosen_xpath = potentially_better_friendly_chosen_xpath
                        if not chosen_element or chosen_element.count() < 1:
                            print('Third attempt in traj failed')
                            chosen_element = get_element(page, potentially_better_chosen_xpath)
                            chosen_xpath = potentially_better_chosen_xpath
                            if not chosen_element or chosen_element.count() < 1:
                                print('Fourth attempt in traj failed')
                                chosen_element = get_element(page, chosen_action.friendly_xpath)
                                chosen_xpath = chosen_action.friendly_xpath
                                if not chosen_element or chosen_element.count() < 1:
                                    print('Fifth attempt in traj failed')
                                    chosen_element = get_element(page, chosen_action.xpath)
                                    chosen_xpath = chosen_action.xpath

                chosen_action_screenshot, screenshot_success = take_screenshot(page)

                if chosen_element and chosen_element.count() > 0 and chosen_xpath:
                    try:
                        scroll_into_view(chosen_element)
                        chosen_action_screenshot, screenshot_success = take_screenshot(page)
                    except Exception as e:
                        print("SCROLL FAILED DURING TRAJECTORY")
                        print(e)

                    if screenshot_success:
                        to_box_coords = None
                        try:
                            # to_box_item = page.locator(f"xpath={action.friendly_xpath}")
                            # if final_element and final_element.count() > 0:  # should be redundant given continue above
                            to_box_coords = chosen_element.bounding_box(timeout=10000)
                        except Exception as e:
                            print(f'GETTING BOUNDING BOXES FAILED FOR IN TRAJ {chosen_action}')
                            print(e)

                        trajectory_action_screenshot = create_boundingbox(chosen_action_screenshot, to_box_coords)
                else:
                    print(f"This action was not found: {chosen_action}")
                    print('Could not find item in trajectory')

                if not screenshot_success:  # TODO BOUNDING BOX FOR THE SCREENSHOT IF SUCCESS
                    print('action screenshot failed')
            else:
                type_list = chosen_indefinite.type_list

            # NOTE: chosen_action type is no longer assigned in match_actions in url_state_manager
            if wait:
                # print(chosen_action)
                input("ABOUT TO DO ACTION")

            if chosen_action.action_type == Action.Type.STOP:
                keep_running = False
                print("STOPPING")
                break

            success = apply_action(page, chosen_action, trajectory_action_screenshot, chosen_element, chosen_xpath,
                                       type_list)
            if wait:
                input("DID ACTION")

            if not success:
                print(f"This action was broken: {chosen_action}")
                keep_running = False
            if wait:
                do_keep_running = input('want to keep running?')
                if do_keep_running != '':
                    keep_running = False

            # def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None)
            # apply_action(page, chosen_action, page.screenshot(), None, None, None)
        else:
            print("No matched state, why?")