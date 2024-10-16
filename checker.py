from utils.element_utils.element_similarity import element_similarity
# from action import Action
from pathlib import Path
import os
from bs4 import BeautifulSoup
import numpy as np
from PIL import Image, ImageDraw
# import cv2
import copy as cp
import pickle
import re
from models import PageObservation
from classes import *
from scrape7 import *
from playwright.sync_api import sync_playwright


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


def match_action_effects(curr_page_state: PageState,
                         url_state_manager: URLStateManager) -> InferencePageState | None:  # Needless amounts of unrolling and rerolling
    found_state = url_state_manager.get_state(curr_page_state)
    if found_state:
        curr_page_actions = [item for item in curr_page_state.actions]  # (typeList, action)
        new_action_list = found_state.match_actions(curr_page_actions)
        inference_page_state = InferencePageState(curr_page_state.url, curr_page_state.ax_nodes, curr_page_state.html,
                                                  found_state, new_action_list)
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
# scraper_state_file = 'dominos/scraper_state.pkl'
# url_state_manager = load_scraper_state(scraper_state_file)
# counter = 0
# for url_state in url_state_manager.urls.values():
#     samples = url_state.unique_samples.values()
#     for sample in samples:
#         # sample is a list of scrape actions
#         for scrape_action in sample:
#             counter += 1
#             action = scrape_action.action
#             if element_similarity('<button data-quid="overlay-no-thanks" class="waterfall-upsell__no-thanks btn btn--outline">No, Go to Checkout</button>', action.html) >= 0.9:
#                 print(action.html)
#                 input('give it a moment')

# print(counter)