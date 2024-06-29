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

def match_action_effects(curr_page_state: PageState, url_state_manager: URLStateManager) -> InferencePageState | None:  # Needless amounts of unrolling and rerolling
    found_state = url_state_manager.get_state(curr_page_state)
    if found_state:
        curr_page_actions = [item for item in curr_page_state.actions]  # (typeList, action)
        new_action_list = found_state.match_actions(curr_page_actions)
        '''
        
        @dataclass
        class InferenceAction:
            curr_action: Action
            type_list: list[Action.Type] | None
            matched_scrape_action: Action
            
        @dataclass
        class PageState:
            url: str
            ax_nodes: list[AxNode]
            html: str
            actions: list[IndefiniteAction]
            header_html: str
            footer_html: str
            
        @dataclass
        class IndefiniteAction:
            type_list: list[Action.Type]
            action: Action | None

        @dataclass
        class InferencePageState:
            url: str
            ax_nodes: list[AxNode]
            html: str
            matched_actions: list[InferenceAction]

        '''
        inference_page_state = InferencePageState(curr_page_state.url, curr_page_state.ax_nodes, curr_page_state.html, found_state, new_action_list)
        return inference_page_state

    else:
        print("NOTHING FOUND")
        return None


scraper_state_file = 'dominos/scraper_state.pkl'
url_state_manager = load_scraper_state(scraper_state_file)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context, page, cdpSession = create_new_context_and_page(browser, None)
    page.goto('https://www.dominos.com/en/')
    wait_for_load(page)
    curr_page_state = get_page_state(page, cdpSession)
    # if found:
    #     for key in found.unique_samples:
    #         print(type(key))
    #         # break
    tonk = match_action_effects(curr_page_state, url_state_manager)

    # input(tonk.url_state)

    # input(tonk.matched_actions[-1].curr_action.action.html)
    # input(tonk.matched_actions[-1].matched_scrape_action.action.html)