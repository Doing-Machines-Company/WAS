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

def match_action_effects(curr_page_state, url_state_manager) -> PageState:  # Needless amounts of unrolling and rerolling
    found = url_state_manager.get_state(curr_page_state)
    if found:
        curr_page_actions = [item[1] for item in curr_page_state.actions]  # (typeList, action)
        matches = found.match_actions(curr_page_actions)
        new_action_list = list()
        # PageState.actions: list[(list[Action.Type], Action)]
        # print(type(matches[0][0]))  # ACTION TYPE
        # print(type(matches[0][1]))  # ACTION INFO TYPE
        # NEED TO ADD SCRAPED TYPE TO SCRAPED RESULT
        for i, (action, matched_action_info) in enumerate(matches):  # DOESN'T RUN WITH NO ACTION EFFECT IN ACTION INFO
            # TODO NEEDS MORE TESTING AFTER ACTION EFFECTS EXIST IN ACTION INFO
            if matched_action_info:
                action.set_action_effect(matched_action_info.action_effect)
                action_type_in_list = [matched_action_info.action.Type]
                new_action_list.append((action_type_in_list, action))
            else:
                new_action_list.append((curr_page_state.actions[i][0], action))

        curr_page_state.actions = new_action_list
        return curr_page_state

    else:
        print("NOTHING FOUND")
        return None


scraper_state_file = 'scraper_state.pkl'
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
    match_action_effects(curr_page_state, url_state_manager)

    # print(found)