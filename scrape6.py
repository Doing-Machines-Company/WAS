import time
from queue import Queue
import threading
from drivers import AxObservation
from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Dialog, TimeoutError
import pickle
from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from scrapecode.page_similarity import page_similarity
from scrapecode.element_similarity import element_similarity
import re
import os
from bs4 import BeautifulSoup
import numpy as np
from PIL import Image, ImageDraw
import cv2
import copy as cp
from scrape_llm import use_gpt_fill_input

#TODO:
#fix equivalence class representations
#thread compliance compliance with action stack/queue
#combine locks into single context lock
#A* (LLM-guided) scrape?


PlaywrightPage = Any
CDPSession = Any
AxNode = Any  # TODO: make this a dataclass

@dataclass
class ActionInfo:
    action: Action
    before_html: str
    after_html: str
    before_screenshot: bytes | str
    after_screenshot: bytes | str
    url: str

@dataclass
class Chunk:
    description: str
    start_identifier: list[str] | None
    end_identifier: list[str] | None
    ordered_candidates: list[str]

@dataclass
class PageState:
    url: str
    html: str
    actions: list[(list[Action.Type], Action)]
    header_html: str
    footer_html: str
#removed some of the fields from pagestate, not sure if they will ultimately be needed?

class EquivalenceClass:
    def __init__(self):
        self.page_urls = set()
        self.page_states: dict[str, PageState] = {}
        self.unique_actions: dict[str, ActionInfo] = {}

    def add_page(self, state: PageState):
        normalized_url = normalize_url(state.url)
        self.page_urls.add(normalized_url)
        self.page_states[normalized_url] = state

    def update_unique_actions(self, actions: list[Action], before_html: str, after_html: str, before_screenshot: bytes, after_screenshot: bytes, url: str):
        for action in actions:
            action_key = action.html
            if action_key not in self.unique_actions or not self.has_similar_action(action):
                self.unique_actions[action_key] = ActionInfo(action, before_html, after_html, before_screenshot, after_screenshot, url)

    def has_similar_action(self, action: Action) -> bool:
        return any(element_similarity(action.html, a.action.html) >= 0.9 for a in self.unique_actions.values())

    def is_new_action(self, action: Action) -> bool:
        return not self.has_similar_action(action)

    def is_similar(self, url: str, html: str) -> bool:
        normalized_url = normalize_url(url)
        if normalized_url in self.page_urls:
            return True

        for page_url in self.page_urls:
            if page_similarity(html, self.page_states[page_url].html) < 0.8:
                return False

        return True


class EquivalenceClassSet:
    def __init__(self):
        self.classes: list[EquivalenceClass] = []
        self.added_urls: set[str] = set()
        self.common_actions = []

    def get_class(self, url: str, html: str) -> Optional[EquivalenceClass]:
        for eq_class in self.classes:
            if eq_class.is_similar(url, html):
                return eq_class
        return None

    def add_page(self, state: PageState, eq_class: Optional[EquivalenceClass]) -> EquivalenceClass:
        self.added_urls.add(normalize_url(state.url))
        if eq_class is None:
            eq_class = EquivalenceClass()
            self.classes.append(eq_class)
        eq_class.add_page(state)
        return eq_class


def get_ax_tree(cdpSession: CDPSession) -> list[AxNode]:
    accessibility_tree = cdpSession.send(
        "Accessibility.getFullAXTree", {}
    )["nodes"]
    seen_ids = set()
    _accessibility_tree = []
    for node in accessibility_tree:
        if node["nodeId"] not in seen_ids:
            _accessibility_tree.append(node)
            seen_ids.add(node["nodeId"])
    accessibility_tree = _accessibility_tree
    for node in accessibility_tree:
        if "backendDOMNodeId" not in node:
            continue
        backend_node_id = str(node["backendDOMNodeId"])
        try:
            remote_object = cdpSession.send(
                "DOM.resolveNode", {"backendNodeId": int(backend_node_id)}
            )
            remote_object_id = remote_object["object"][
                "objectId"]  # MAY BE ABLE TO FIND ELEMENT GIVEN REMOTE OBJECT ID, NO NEED FOR XPATHS
            xpath_script = '''
                    function() {
                        function getXPath(element) {
                            if (!element || !element.parentNode) {
                                return null;
                            }
                            if (element.id) {
                                return 'id("' + element.id + '")';
                            }
                            if (element === document.body) {
                                return element.tagName.toLowerCase();
                            }
                            var ix = 0;
                            var siblings = element.parentNode.childNodes;
                            for (var i = 0; i < siblings.length; i++) {
                                var sibling = siblings[i];
                                if (sibling === element) {
                                    return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                }
                                if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                                    ix++;
                                }
                            }
                        }
                        return getXPath(this);
                    }
                    '''

            xpath_response = cdpSession.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": remote_object_id,
                    "functionDeclaration": xpath_script,
                    "returnByValue": True
                }
            )
            node_xpath = xpath_response["result"]["value"]
            response = cdpSession.send(
                "DOM.getOuterHTML",
                {
                    "objectId": remote_object_id,
                },
            )
            node["html"] = response["outerHTML"]
            node["xpath"] = node_xpath

        except Exception as e:
            node['xpath'] = ''
            if 'html' not in node:
                node['html'] = ''
            continue

    return accessibility_tree


def create_boundingbox(image_bytes, bounding_box):
    if not bounding_box:
        print("FOR SOME REASON NO BOUNDING BOX")
        return image_bytes
    else:
        print(f"BOUNDING BOX: {bounding_box}")
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    x, y, width, height = bounding_box['x'], bounding_box['y'], bounding_box['width'], bounding_box['height']
    top_left = (int(x), int(y))
    bottom_right = (int(x + width), int(y + height))
    color = (0, 255, 0)
    thickness = 2

    cv2.rectangle(img, top_left, bottom_right, color, thickness)

    # cv2.imwrite('testtest.png', img)

    _, buffer = cv2.imencode('.png', img)
    return buffer.tobytes()


def ax_node_to_action(ax_node: AxNode, header_html: str, footer_html: str, url: str) -> (list[Action.Type], Action):

    possible_action_types = []

    important_clickables = [
        'button',
    ]

    general_clickables = [  # dialog clickable?
        'menuitem',
        'treeitem', 'switch', 'option', 'menuitemcheckbox',
        'menuitemradio',
        'slider', 'listbox', 'tree',
        'grid', 'alert', 'alertdialog',
        'log', 'marquee', 'timer', 'tooltip', 'banner',
        'complementary', 'contentinfo', 'form', 'main', 'navigation',
        'region', 'status', 'img', 'note', 'application',
        'article', 'cell', 'definition', 'directory', 'document',
        'feed', 'figure', 'group', 'img', 'list',
        'listitem', 'math', 'progressbar',
        'separator', 'toolbar', 'tooltip', 'presentation', 'option', 'tab']

    input_roles = [
        'textbox',
        'checkbox', 'radio',
        'textarea'
    ]

    non_browser_attributes = [
        'mailto:',
        'tel:',
        'print()',
        'window.print()',
        'onclick="window.print()"',
        'printthis()',
        'onclick="printthis()"',
    ]

    xpath = ax_node["xpath"]
    html = ax_node["html"]
    role = ax_node["role"]

    soup = BeautifulSoup(html, 'html.parser')

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        # Check if the action is a pure link in the header or footer
        if html in footer_html or (html in header_html and url not in 'https://www.dominos.com/en/'):
            return ([], None)

        #not sure what this does at all - Cem
        if any(attr in html.lower() for attr in non_browser_attributes):
            return ([], None)

        if role.strip() == 'link':
            possible_action_types.append(Action.Type.CLICK_LINK)

        elif role.strip() in important_clickables:
            possible_action_types.append(Action.Type.CLICK_IMPORTANT)

        elif role.strip() == 'radio':
            action = Action(Action.Type.CLICK_RADIO, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_RADIO)

        elif role.strip() == 'checkbox':
            possible_action_types.append(Action.Type.CLICK_CHECKBOX)

        elif role.strip() in general_clickables:
            action = Action(Action.Type.CLICK_GENERAL, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_GENERAL)

        elif role.strip() in input_roles or soup.find(('input', 'textarea', 'select')):

            input_type = None

            input_element = soup.find('input')

            if input_element:
                input_type = input_element.get('type', '').lower()

            if input_type == 'checkbox' and Action.Type.CLICK_CHECKBOX not in possible_action_types:
                possible_action_types.append(Action.Type.CLICK_CHECKBOX)

            elif input_type == 'radio' and Action.Type.CLICK_RADIO not in possible_action_types:
                possible_action_types.append(Action.Type.CLICK_RADIO)

            else:
                possible_action_types.append(Action.Type.INPUT)


        elif soup.has_attr('contenteditable') and soup['contenteditable'].lower() == 'true':
            possible_action_types.append(Action.Type.INPUT)

    if possible_action_types != []:
        action = Action(None, xpath, html)
        action.set_tree_line(f"{role}: {ax_node['name']}")
        return (possible_action_types, action)
    else:
        return ([], None)



def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, friendly_xpath, backup_friendly_xpath=None, possible_types=None) -> (bool, Action):  # TODO handle multiple possible action types
    for a_type in possible_types:
        try:
            if a_type in [Action.Type.CLICK_LINK, Action.Type.CLICK_IMPORTANT, Action.Type.CLICK_CHECKBOX,
                               Action.Type.CLICK_RADIO, Action.Type.CLICK_GENERAL]:
                if friendly_xpath:
                    try:
                        page.evaluate(
                            f"() => {{ let e = document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
                        a.action_type = a_type  # probs not good
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via JavaScript click: {e}")

                    try:
                        page.locator(f"xpath={friendly_xpath}").click(timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via Playwright locator.click: {e}")

                if backup_friendly_xpath:
                    try:
                        page.evaluate(
                            f"() => {{ let e = document.evaluate('{backup_friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
                        a.action_type = a_type  # probs not good
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via JavaScript click: {e}")

                    try:
                        page.locator(f"xpath={backup_friendly_xpath}").click(timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via Playwright locator.click: {e}")

            elif a_type == Action.Type.INPUT:
                if friendly_xpath:
                    try:
                        input_element = page.locator(f"xpath={friendly_xpath}")
                        input_fill = use_gpt_fill_input('None', before_screenshot, a.html, True)
                        input_element.fill(input_fill, force=True, timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error inputting text into element: {e}")

                if backup_friendly_xpath:
                    try:
                        input_element = page.locator(f"xpath={backup_friendly_xpath}")
                        input_fill = use_gpt_fill_input('None', before_screenshot, a.html, True)
                        input_element.fill(input_fill, force=True, timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error inputting text into element: {e}")

            elif a_type == Action.Type.GOTO_URL:
                try:
                    page.goto(a.input_string, timeout=5000)
                    page.wait_for_load_state('networkidle', timeout=5000)
                    a.action_type = a_type
                    return True, a
                except Exception as e:
                    print(f"Error navigating to URL: {e}")

            elif a_type == Action.Type.GO_BACK:
                pass
                # try:
                #     page.go_back(), timeout=5000
                #     page.wait_for_load_state('networkidle', timeout=5000)
                #     return True, action_type
                # except Exception as e:
                #     print(f"Error going back: {e}")
                page.goto(a.input_string)
                page.wait_for_load_state('networkidle')

        except Exception as e:
            print(f"Unhandled exception for action type {a_type}: {e}")

    return False, a


# this is the aggressive normalization
def normalize_url(url: str) -> str:
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment


def get_page_state(page: PlaywrightPage, cdpSession: CDPSession) -> PageState:

    # Navigate to the given URL and wait for the page to load
    wait_for_load(page)

    # Retrieve the accessibility tree and create an AxObservation object
    cleaned = AxObservation(get_ax_tree(cdpSession), page.url)
    #DON'T PRINT FOR NOW, IT'S CLUTTERING EVERYTHING
    # print(cleaned)

    # Extract the header and footer HTML
    header_html = page.evaluate("document.getElementsByTagName('header')[0]?.outerHTML || ''")
    footer_html = page.evaluate("document.getElementsByTagName('footer')[0]?.outerHTML || ''")
    #currently page specific

    # Extract actions from the accessibility nodes and filter out None values, only scrape header and footer on homepage
    # actions = [ax_node_to_action(node, header_html if page.url not in 'https://www.dominos.com/en/' else '', footer_html if page.url not in 'https://www.dominos.com/en/' else '') for node in cleaned.nodes_info]
    indefinite_actions = [ax_node_to_action(node, header_html, footer_html, page.url) for node in cleaned.nodes_info]

    new_indefinite_actions = []
    for tL, a in indefinite_actions:
        if a is not None and tL != []:
            new_indefinite_actions.append((tL, a))
    # indefinite_actions = [(tL, a) for (tL, a) in indefinite_actions if tL != []]  # TODO now a list of lists of actions



    # Create and return a PageState object with the normalized URL, HTML content, actions, header HTML, and footer HTML
    return PageState(
        url=page.url,
        html=page.content(),
        actions=new_indefinite_actions,
        header_html=header_html,
        footer_html=footer_html
    )




def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race
def explore_page(url: str, equiv_classes_lock: threading.Lock, eq_class_lock: threading.Lock,
                 page_queue_lock: threading.Lock,
                 seen_urls_lock: threading.Lock, equiv_classes: EquivalenceClassSet, url_queue: Queue, seen_urls: set[str],
                 browser, cookies, root: str, thread_id: int, idle_flags: dict):

    # context = browser.new_context(
    #     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
    # page = context.new_page()  # instead of making page here, make page in explore_page
    # cdpSession = context.new_cdp_session(page)
    #
    # if cookies is not None:
    #     context.add_cookies(cookies)

    def create_new_context_and_page(browser, cookies):
        context = browser.new_context(
            permissions=[], #this is to prevent popups
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        if cookies is not None:
            context.add_cookies(cookies)
        page = context.new_page()
        cdpSession = context.new_cdp_session(page)
        return context, page, cdpSession

    idle_flags[thread_id] = False


    with seen_urls_lock:
        if normalize_url(url) in seen_urls:
            return
        seen_urls.add(normalize_url(url))
    #TODO: ROOT MAY TAKE DIFFERENT FORMS, FIX THIS
    def root_check(url_item, root_item):
        parsed_url = urlparse(url_item)
        # return root_item in parsed_url.netloc if parsed_url.netloc else False
        return root_item == parsed_url.netloc if parsed_url.netloc else False

    try:  # this really shouldn't ever fail
        is_in_root = root_check(url, root)
        if not is_in_root:
            print(f"Skipping page outside of root: {url}")
            return
    except:
        print(f"Root check failed, skipping: {url}")
        return


    #we use trajectory to track the sequence of actions needed to trigger the
    #creation of any actions that do not readily exist on the base/unmodified
    #version of the website



    #out of a set of actions generated from an observation, removes duplicates.
    #does not remove duplicates in header or footer because they are generally
    #significant enough that we want to keep them
    def get_unique_actions(new_state):            
        sample_size = 3 #maximum number of samples to include among similar actions
        unique_actions = []
        new_actions = new_state.actions
        header_html = new_state.header_html
        footer_html = new_state.footer_html
        for (possible_types, action) in new_actions:
            if action.html in header_html or action.html in footer_html:
                unique_actions.append([(possible_types, action)]) #add header/footer items to own sample
            else:
                unique = True
                for samples in unique_actions:
                    if any(element_similarity(action.html, sample.html) >= 0.9 for (tL, sample) in samples):
                        if len(samples) < sample_size:
                            samples.append((possible_types,action))
                        unique = False
                        break
                if unique:
                    unique_actions.append([(possible_types, action)])
        return unique_actions

    def get_xpath_by_outer_html(page, outer_html):
        # JavaScript function to find the element by outerHTML and generate its XPath
        js_code = """
        (outerHTML) => {
            function getElementXPath(element) {
                if (element.id !== '') {
                    return 'id("' + element.id + '")';
                }
                if (element === document.body) {
                    return element.tagName.toLowerCase();
                }
                var ix = 0;
                var siblings = element.parentNode.childNodes;
                for (var i = 0; i < siblings.length; i++) {
                    var sibling = siblings[i];
                    if (sibling === element) {
                        return getElementXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                        ix++;
                    }
                }
            }
            var element = Array.from(document.querySelectorAll('*')).find(el => el.outerHTML === outerHTML);
            if (element) {
                return getElementXPath(element);
            }
            return null;
        }
        """
        # Evaluate the JavaScript code in the context of the page
        xpath = page.evaluate(js_code, outer_html)
        return xpath

    def explore_actions():
        context, page, cdpSession = create_new_context_and_page(browser, cookies)
        try:
            page.goto(url)
            wait_for_load(page, load_time_ms=3000)
        except Exception as e:
            print(f"Error navigating to page: {url}. Error: {e}")
            return
        #basically scrape_flag is do we need to keep scraping this page
        scrape_flag = False
        print("*" * 80)
        print("Exploring ", url)

        try:
            before_state = get_page_state(page, cdpSession)
        except Exception as e:
            print(f"Error getting page state: {url}. Error: {e}")
            return
        #REMEMBER TO HANDLE EQUIVALENCE CLASS CODE - CEM !!!!
        with equiv_classes_lock:
            eq_class = equiv_classes.get_class(before_state.url, before_state.html)

            if eq_class is None:
                scrape_flag = True
                eq_class = equiv_classes.add_page(before_state, None)
        with eq_class_lock:
            new_actions = [(tL, a) for (tL, a) in before_state.actions if eq_class.is_new_action(a)]
            if len(new_actions) > 0:
                scrape_flag = True

        if scrape_flag:

            #used to check whether an action has already been queued yet (if seen again, we shouldn't requeue)
            seen_actions = []
            #data structure to control flow of new actions
            action_queue = Queue()

            unique_actions = get_unique_actions(before_state)  # should check typing

            #at this point, seen_actions is empty, so we can just put the unique actions into the queue
            for samples in unique_actions:
                action_queue.put(samples)
            #we can just set seen_actions since it is empty
            #TO IMPROVE EFFICIENCY MAYBE JUST SET THIS TO STRICTLY UNIQUE  - CEM
            seen_actions = unique_actions
            while action_queue.qsize() > 0:
                samples = action_queue.get(timeout=0.5)  # possible_types should have some sort of importance ordering
                sample_action_infos : list[ActionInfo] = []
                for possible_types, action in samples:
                    if not action.xpath:
                        print(f"Skipping action without XPath: {action}")
                        continue

                    page.evaluate("""
                        window.print = function() {
                            console.log('Print was triggered');
                        };
                    """)

                    friendly_xpath = action.xpath if '(' in action.xpath.split("/")[0] else f"//{action.xpath}"

                    '''
                    
                    Error clicking element via javascript click: TypeError: Cannot read properties of null (reading 'scrollIntoViewIfNeeded')
                    at eval (eval at evaluate (:226:30), <anonymous>:1:181)
                    at UtilityScript.evaluate (<anonymous>:233:19)
                    at UtilityScript.<anonymous> (<anonymous>:1:44)
                    
                    I want to scroll to what I'm interacting with before I interact, for action effect reasons.
                    
                    '''
                    page.reload()
                    time.sleep(2)
                    #need sleep here for going between different contexts for some reason

                    print("-" * 80)
                    # print("Action: ", action.html)
                    print("Page url: ", page.url)
                    print("Ax object", action.tree_line)
                    print("Trajectory: ", action.display_trajectory())
                    traj_success = True
                    if action.trajectory:
                        print("***Executing Trajectory***")
                    for traj_action in action.trajectory:
                        #  TODO Need to get new good xpath for action
                        backup_xpath = get_xpath_by_outer_html(page, traj_action.html)
                        if backup_xpath:
                            backup_friendly_xpath = backup_xpath if '(' in backup_xpath.split("/")[0] else f"//{backup_xpath}"
                            success, action = apply_action(page, traj_action, page.screenshot(), backup_friendly_xpath, traj_action.friendly_xpath, [traj_action.action_type])
                        else:
                            success, action = apply_action(page, traj_action, page.screenshot(), traj_action.friendly_xpath,
                                                        None, [traj_action.action_type])
                        if not success:
                            print(traj_action)
                            print("Trajectory broken, skipping")
                            traj_success = False
                            break
                        wait_for_load(page, load_time_ms=3000)
                    if not traj_success:
                        continue
                    before_screenshot = page.screenshot()
                    friendly_element = page.evaluate(
                        f"document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue")

                    if friendly_element:
                        page.evaluate(
                            f"document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.scrollIntoViewIfNeeded();")
                    else:
                        element = page.evaluate(
                            f"document.evaluate('{action.xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue")
                        if element:
                            page.evaluate(
                                f"document.evaluate('{action.xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.scrollIntoViewIfNeeded();")
                        else:
                            print(f"Element not found for XPath: {action.xpath}, Ax object: {action.tree_line}")
                            continue
                    action.set_friendly_xpath(friendly_xpath)
                    #  fix screenshot here
                    # print(type(before_screenshot))

                    to_box_coords = None
                    try:
                        to_box_item = page.locator(f"xpath={action.xpath}")
                        to_box_coords = to_box_item.bounding_box(timeout=5000)
                    except Exception as e:
                        print(e)

                    before_screenshot = create_boundingbox(before_screenshot, to_box_coords)
                    # print(type(before_screenshot))
                    success, action = apply_action(page, action, before_screenshot, friendly_xpath, None, possible_types)
                    if not success:
                        print(f"This action was not successful: {action.html}")
                        continue  # hopefully no issues with this

                    wait_for_load(page, load_time_ms=3000)
                    if len(page.context.pages) > 1 and page.context.pages[-1] != page:
                        new_page = page.context.pages[-1]
                        after_screenshot = new_page.screenshot(full_page=False)
                        sample_action_infos.append(ActionInfo(action, before_state.html, new_page.content(), before_screenshot, after_screenshot, url))
                        with page_queue_lock:
                            with seen_urls_lock:
                                if normalize_url(new_page.url) not in seen_urls:
                                    #REMEMBER TO ADD BACK THIS LINE IMMEDIATELY
                                    # url_queue.put(new_page.url)  # Adds stuff to be scraped
                                    #  Make sure everything is discovered, unknown unknowns

                                    print(new_page.url)
                        new_page.close()
                    else:
                        after_screenshot = page.screenshot(full_page=False)
                        sample_action_infos.append(ActionInfo(action, before_state.html, page.content(), before_screenshot, after_screenshot, url))
                            

                    #the url is being normalized a bit too aggressively to the point
                    #that pages that are clearly different are being put into the same eq
                    #because normalized url is the same
                    # if normalize_url(before_state.url) != normalize_url(page.url):
                    if before_state.url != page.url:
                        with page_queue_lock:
                            with seen_urls_lock:
                                if normalize_url(page.url) not in seen_urls:
                                    # url_queue.put(page.url)
                                    print(page.url)
                    else:
                        #since we stayed on the same page we want to see if applying
                        #this action generated new content on the page
                        try:
                            new_state = get_page_state(page, cdpSession)
                            new_actions = get_unique_actions(new_state)

                            #take the set difference unique_actions \ seen_actions
                            #it is fine to just compare one action from each sample, since we assume transitive similarity
                            difference = [sample for sample in new_actions if not any(element_similarity(sample[0][1].html, seen_sample[0][1].html) for seen_sample in seen_actions)]
                            #put the difference onto the queue
                            new_trajectory = []
                            if difference:
                                new_trajectory = cp.deepcopy(action.trajectory)
                                new_trajectory.append(action)
                                print("***Detected new actions***")
                            for sample in difference:
                                print("New sample")
                                for dTl, different_action in sample:
                                    print("\tNew action: ", different_action.tree_line)
                                    #update trajectory with parent's trajectory + parent
                                    different_action.set_trajectory(new_trajectory)
                                action_queue.put(sample)
                            #put the difference into the seen_actions, effectively unique_actions U seen_actions
                            seen_actions += difference
                        except Exception as e:
                            print(f"Error getting page state after applying {action.tree_line} at {url}. Error: {e}")
                            return
                    cdpSession.detach()
                    page.close()
                    context.close()

                    context, page, cdpSession = create_new_context_and_page(browser, cookies)

                    page.goto(before_state.url)  # this threw an error once, idk why
                    time.sleep(2)
                if sample_action_infos: #the only reason sample_action_infos may be empty is if the action errored out and never got added
                    with eq_class_lock:
                        representative_html = sample_action_infos[0].action.html
                        if representative_html not in eq_class.unique_actions:
                            eq_class.unique_actions[representative_html] = sample_action_infos

        #  finally close here
        cdpSession.detach()
        page.close()
        context.close()
        #remove this, only here for testing


        #NEED TO ACTUALLY UPDATE THE ACTIONS, THEY ARE ONLY ADDED AT THE BEGINNING - Cem


    explore_actions()
    if url_queue.empty() and url_queue.qsize() <= 0:
        idle_flags[thread_id] = True


def worker(thread_id: int, idle_flags: dict, url_queue: Queue, equiv_classes_lock: threading.Lock, eq_class_lock: threading.Lock, page_queue_lock: threading.Lock, seen_urls_lock: threading.Lock, equiv_classes: EquivalenceClassSet, seen_urls: set[str], headless: bool, cookies: Optional[dict], root: str, stop_event: threading.Event):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # context = browser.new_context(
        #     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        # page = context.new_page()  # instead of making page here, make page in explore_page
        # cdpSession = context.new_cdp_session(page)

        # if cookies is not None:
        #     context.add_cookies(cookies)

        while not stop_event.is_set():
            url = None
            try:
                url = url_queue.get(timeout=0.5)  # Reduced timeout value
            except Exception as e:
                idle_flags[thread_id] = True
                continue

            if url is not None:
                explore_page(url, equiv_classes_lock, eq_class_lock, page_queue_lock, seen_urls_lock, equiv_classes,
                             url_queue, seen_urls, browser, cookies, root, thread_id, idle_flags)
                time.sleep(2)
                url_queue.task_done()
            else:
                idle_flags[thread_id] = True
            if stop_event.is_set():
                break

            time.sleep(1)

        print(f"worker Thread-{thread_id} fucking off")
        browser.close()

def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'dominos', root: str = "", num_threads: int = 10):
    def save_equivalence_classes(equiv_classes: EquivalenceClassSet, output_dir: str):  #  Update the folders so it groups them by URL, replace/modify the url as paths can't take in slashes
        # Create the output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Save the screenshots separately and update the file paths
        for eq_class in equiv_classes.classes:
            for key, action_infos in eq_class.unique_actions.items():
                action_info = action_infos[0]
                sample_path = Path (output_dir) / Path (normalize_url(action_info.url)) / (action_info.action.tree_line + str(hash(key)))  # root / url / curraction, make new url folder if it doesn't exist
                sample_path.mkdir(parents = True, exist_ok = True)
                for action_info in action_infos:
                    subdir_path = sample_path / (action_info.action.tree_line + str(hash(key)))
                    subdir_path.mkdir(parents = True, exist_ok = True)
                    before_screenshot_filename = f"action_{hash(key)}_before.png"
                    before_screenshot_path = subdir_path / before_screenshot_filename
                    with open(before_screenshot_path, 'wb') as f:
                        f.write(action_info.before_screenshot)
                    action_info.before_screenshot = str(before_screenshot_path)

                    after_screenshot_filename = f"action_{hash(key)}_after.png"
                    after_screenshot_path = subdir_path / after_screenshot_filename
                    with open(after_screenshot_path, 'wb') as f:
                        f.write(action_info.after_screenshot)
                    action_info.after_screenshot = str(after_screenshot_path)

                    with open(Path(subdir_path) / 'info.txt', 'w') as f:
                        f.write(f"URL: {action_info.url}\n")
                        f.write(f"XPATH: {action_info.action.friendly_xpath}\n")
                        f.write(f"TRAJECTORY: {action_info.action.trajectory}\n\n")
                        f.write(f"HTML: {action_info.action.html}\n")
        # Save the EquivalenceClassSet object using pickling
        output_path = Path(output_dir) / 'scraper_state.pkl'
        with open(output_path, 'wb') as f:
            pickle.dump(equiv_classes, f)

    # Initialize an EquivalenceClassSet to store and manage equivalence classes
    equiv_classes = EquivalenceClassSet()
    equiv_classes_lock = threading.Lock()
    eq_class_lock = threading.Lock()
    page_queue_lock = threading.Lock()
    seen_urls_lock = threading.Lock()

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    seen_urls = set()

    url_queue = Queue()
    url_queue.put(starting_url)

    stop_event = threading.Event()

    threads = []
    idle_flags = dict()
    for i in range(num_threads):
        thread_id = f"Thread-{i}"
        idle_flags[thread_id] = False
        t = threading.Thread(target=worker,
                             args=(thread_id, idle_flags, url_queue, equiv_classes_lock, eq_class_lock, page_queue_lock,
                                   seen_urls_lock,
                                   equiv_classes, seen_urls,
                                   headless, cookies, root, stop_event))
        t.start()
        threads.append(t)

    while True:
        if url_queue.empty() and all(idle_flags[i] for i in idle_flags) and url_queue.qsize() <= 0:
            time.sleep(1)
            stop_event.set()
            break
        else:
            time.sleep(1)

    for t in threads:
        t.join()


    save_equivalence_classes(equiv_classes, output_dir)
    print(url_queue.qsize())
    print(seen_urls)

num_cores = os.cpu_count()

explore("https://www.dominos.com/en/restaurants", headless=False, root="www.dominos.com", num_threads=1)