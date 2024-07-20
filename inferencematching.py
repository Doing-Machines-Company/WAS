from scrapecode.element_similarity import element_similarity
# from action import Action
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
from classes import *
from scrape7 import *
from playwright.sync_api import sync_playwright
from inferenceagent import *



def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)

def load_scraper_state(file_path: str):
    with open(file_path, 'rb') as f:
        return pickle.load(f)

def match_tree_to_scrape(page, equiv_class_set):
    curr_page_html = page.content()
    curr_page_html = page.content()
    equiv_class_set.get_class(page.url, curr_page_html)

def create_new_context_and_page(browser, cookies):
    context = browser.new_context(
        permissions=[],  # this is to prevent popups
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
    if cookies is not None:
        context.add_cookies(cookies)
    page = context.new_page()
    cdpSession = context.new_cdp_session(page)
    return context, page, cdpSession

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
task = 'buy me a pizza'
keep_running = True
task_mem = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context, page, cdpSession, login_success = setup_context(browser, None)
    page.goto('https://www.dominos.com/')
    wait_for_load(page)
    while keep_running:
        trajectory_action_screenshot = None
        chosen_element = None
        chosen_xpath = None
        curr_page_state = get_page_state(page, cdpSession)
        matched_inference_state = match_action_effects(curr_page_state, url_state_manager)
        if matched_inference_state:
            stop_action = Action(Action.Type.STOP, None, None)
            stop_action.set_special_effect('Stop trying to perform user task and finish')
            stop_indefinite = IndefiniteAction([Action.Type.STOP], stop_action, None)
            special_actions = [stop_indefinite]
            tree = InferenceAxtree(matched_inference_state, special_actions=special_actions, use_scrape=True)
            print(tree.get_debug_tree())
            answer = call_agent(task, tree, task_mem)
            print(f"THIS ONE: {answer}")
            if answer is None:
                raise Exception
            chosen_action_index = answer[0]
            page_purpose = answer[1]
            acted_object = answer[2]
            new_memory = LinearMemory(tree.get_action_effect_from_index(chosen_action_index), page_purpose, acted_object)
            task_mem.append(new_memory)
            input(str(task_mem))

            chosen_indefinite = tree.get_action_from_index(chosen_action_index)  # TODO MAKE SURE YOU GET ACTION TYPE FROM SCRAPE TIME
            chosen_action = chosen_indefinite.action

            if chosen_indefinite not in special_actions:
                if chosen_action.action_type is not None:
                    type_list = [chosen_action.action_type]
                    for item in chosen_indefinite.type_list:
                        if item not in type_list:
                            type_list.append(item)
                else:
                    type_list = chosen_indefinite.type_list
                print(type_list)
                print(chosen_action.action_type)
                print(chosen_action.xpath)
                print(chosen_action.html)


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

            input("ABOUT TO DO ACTION")

            if chosen_action.action_type == Action.Type.STOP:
                keep_running = False
                print("STOPPING")
                break

            success = apply_action(page, chosen_action, trajectory_action_screenshot, chosen_element, chosen_xpath,
                                       type_list)

            input("DID ACTION")

            if not success:
                print(f"This action was broken: {chosen_action}")
                keep_running = False

            do_keep_running = input('want to keep running?')
            if do_keep_running != '':
                keep_running = False
            # def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None)
            # apply_action(page, chosen_action, page.screenshot(), None, None, None)