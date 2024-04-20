import time
from queue import Queue
import threading
from drivers import AxObservation
from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Dialog
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
import cv2
import copy as cp

#TODO: 
    #trajectory tracking logic 
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
    actions: list[Action]
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

    def update_unique_actions(self, actions: list[Action], before_html: str, after_html: str, before_screenshot: bytes, after_screenshot: bytes):
        for action in actions:
            action_key = action.html
            if action_key not in self.unique_actions or not self.has_similar_action(action):
                self.unique_actions[action_key] = ActionInfo(action, before_html, after_html, before_screenshot, after_screenshot)

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

def create_boundingbox(page, action, screenshot: bytes, friendly_xpath):
    nparr = np.frombuffer(screenshot, np.uint8)  # get numpy array
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Get the current scroll position of the page
    scroll_x, scroll_y = page.evaluate("[window.scrollX, window.scrollY]")

    # Get the bounding box of the element using locator
    locator = page.locator(f"xpath={friendly_xpath}")
    if locator:
        bounding_box = locator.bounding_box()
        if bounding_box:
            x, y, w, h = bounding_box["x"], bounding_box["y"], bounding_box["width"], bounding_box["height"]

            # Adjust the bounding box coordinates based on the scroll position
            x -= scroll_x
            y -= scroll_y

            # Draw the bounding box on the image
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Add the label "1" to the top-left corner of the bounding box
            cv2.putText(img, "1", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # Save debug
    output_path = f"screenshot_with_boundingbox_{action.action_type}.png"
    cv2.imwrite(output_path, img)
    # _, img_encoded = cv2.imencode(".png", img)
    # return img_encoded.tobytes()
def get_input_llm(page, action, before_screenshot, friendly_xpath):

    return 'test input'

def ax_node_to_action(ax_node: AxNode, header_html: str, footer_html: str) -> Optional[Action]:
    important_clickables = [
        'button',
    ]

    general_clickables = [
        'menuitem',
        'treeitem', 'switch', 'option', 'menuitemcheckbox',
        'menuitemradio',
        'slider', 'listbox', 'tree',
        'grid', 'alert', 'alertdialog', 'dialog',
        'log', 'marquee', 'timer', 'tooltip', 'banner',
        'complementary', 'contentinfo', 'form', 'main', 'navigation',
        'region', 'status', 'img', 'note', 'application',
        'article', 'cell', 'definition', 'directory', 'document',
        'feed', 'figure', 'group', 'img', 'list',
        'listitem', 'math', 'progressbar',
        'separator', 'toolbar', 'tooltip', 'presentation', 'option']

    input_roles = [
        'textbox', 'searchbox', 'slider', 'spinbutton', 'radiogroup',
        'checkbox', 'radio', 'switch', 'option', 'listbox',
        'combobox', 'textarea', 'spinbutton'
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
        if role.strip() == 'link' and (html in header_html or html in footer_html):
            return None

        if any(attr in html.lower() for attr in non_browser_attributes):
            return None

        if role.strip() == 'link':
            action = Action(Action.Type.CLICK_LINK, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

        elif role.strip() in important_clickables:
            action = Action(Action.Type.CLICK_IMPORTANT, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

        elif role.strip() == 'radio':
            action = Action(Action.Type.CLICK_RADIO, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

        elif role.strip() == 'checkbox':
            action = Action(Action.Type.CLICK_CHECKBOX, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

        elif role.strip() in general_clickables:
            action = Action(Action.Type.CLICK_GENERAL, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

        elif role.strip() in input_roles or soup.find(('input', 'textarea', 'select')):

            input_type = None

            input_element = soup.find('input')

            if input_element:
                input_type = input_element.get('type', '').lower()

            if input_type == 'checkbox':
                action = Action(Action.Type.CLICK_CHECKBOX, xpath, html)

            elif input_type == 'radio':
                action = Action(Action.Type.CLICK_RADIO, xpath, html)

            else:
                action = Action(Action.Type.INPUT, xpath, html)

            action.set_tree_line(f"{role}: {ax_node['name']}")

            return action

    return None


def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, friendly_xpath) -> bool:
    match a.action_type:
        case Action.Type.CLICK_LINK | Action.Type.CLICK_IMPORTANT | Action.Type.CLICK_CHECKBOX | Action.Type.CLICK_RADIO:
            # friendly_path = a.xpath if '(' in a.xpath.split("/")[0] else f"//{a.xpath}"
            try:
                page.evaluate(
                    f"() => {{ let e = document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.scrollIntoViewIfNeeded(); e.click(); }}")
                return True
            except Exception as e:
                print(f"Error clicking element via javascript click: {e}")

            try:
                page.locator(f"xpath={friendly_xpath}").click()
                return True
            except Exception as e:
                print(f"Error clicking element via playwright xpath locator.click: {e}")
                return False


        case Action.Type.INPUT:
            # # input_text = a.input_string
            # input_text = "test"
            # try:
            #     page.wait_for_load_state('networkidle')
            #     page.locator(f'xpath={a.xpath}').first.fill(input_text)
            #     page.wait_for_load_state('networkidle')
            #     if "search" in a.html:
            #         # print("SEARCHING PRESS ENTER")
            #         page.keyboard.press('Enter')
            #         page.wait_for_load_state('networkidle')
            #
            # except Exception as e:
            #     print(f"Error inputting element: {e}")
            #     return False
            # friendly_path = a.xpath if '(' in a.xpath.split("/")[0] else f"//{a.xpath}"
            try:
                input_element = page.locator(f"xpath={friendly_xpath}")
                input_fill = get_input_llm(page, a, before_screenshot, friendly_xpath)
                # input_fill = 'test input'
                input_element.fill(input_fill)
                return True
            except Exception as e:
                print(f"Error inputting text into element: {e}")
                return False

            return False

        case Action.Type.GET_NEXT_SUBTASK_FINISHED:
            pass

        case Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE:
            pass

        case Action.Type.STOP:
            input("ABOUT TO STOP")
            exit()

        case Action.Type.GOTO_URL:  # haven't tested
            page.goto(a.input_string)
            page.wait_for_load_state('networkidle')

        case Action.Type.GO_BACK:
            # self.page.go_back() not actually using go_back as occasionally the last page is not useful, need to make better this is jank
            page.goto(a.input_string)
            page.wait_for_load_state('networkidle')

    return True


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
    actions = [ax_node_to_action(node, header_html if page.url not in 'https://www.dominos.com/en/' else '', footer_html if page.url not in 'https://www.dominos.com/en/' else '') for node in cleaned.nodes_info]
    actions = [a for a in actions if a is not None]

    # Create and return a PageState object with the normalized URL, HTML content, actions, header HTML, and footer HTML
    return PageState(
        url=page.url,
        html=page.content(),
        actions=actions,
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
                 page: PlaywrightPage, cdpSession: CDPSession, root: str, thread_id: int, idle_flags: dict):

    idle_flags[thread_id] = False

    '''
    explore_page(url, equiv_classes_lock, eq_class_lock, page_queue_lock, seen_urls_lock, equiv_classes,
                        seen_urls, page, cdpSession, root, thread_id, idle_flags)

    :param url:
    :param equiv_classes_lock:
    :param eq_class_lock:
    :param page_queue_lock:
    :param seen_urls_lock:
    :param equiv_classes:
    :param url_queue:
    :param seen_urls:
    :param page:
    :param cdpSession:
    :param root:
    :param thread_id:
    :param idle_flags:
    :return:
    '''
    with seen_urls_lock:
        if normalize_url(url) in seen_urls:
            return
        seen_urls.add(normalize_url(url))
    #TODO: ROOT MAY TAKE DIFFERENT FORMS, FIX THIS
    if root not in url:
        print(f"Skipping page outside of root: {url}")
        return

    try:
        page.goto(url)
        wait_for_load(page, load_time_ms=3000)
    except Exception as e:
        print(f"Error navigating to page: {url}. Error: {e}")
        return
    #we use trajectory to track the sequence of actions needed to trigger the 
    #creation of any actions that do not readily exist on the base/unmodified
    #version of the website



    #out of a set of actions generated from an observation, removes duplicates.
    #does not remove duplicates in header or footer because they are generally 
    #significant enough that we want to keep them 
    def get_unique_actions(new_state):
        unique_actions = []
        new_actions = new_state.actions
        header_html = new_state.header_html
        footer_html = new_state.footer_html
        for action in new_actions:
            if (action.html in header_html or action.html in footer_html 
            or not any(element_similarity(action.html, a.html) >= 0.9 for a in unique_actions)):
                unique_actions.append(action)
        return unique_actions
    
    def explore_actions():
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
            new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
            if len(new_actions) > 0:
                scrape_flag = True

        if scrape_flag:
            
            #used to check whether an action has already been queued yet (if seen again, we shouldn't requeue)
            seen_actions = []
            #data structure to control flow of new actions
            action_queue = Queue()
            
            unique_actions = get_unique_actions(before_state)

            #at this point, seen_actions is empty, so we can just put the unique actions into the queue
            for a in unique_actions:
                action_queue.put(a)
            #we can just set seen_actions since it is empty
            seen_actions = unique_actions
            while action_queue.qsize() > 0:
                action = action_queue.get(timeout=0.5) 
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
                #MIGHT NEED A SLEEP HERE!!!
                
                print("-" * 80)
                # print("Action: ", action.html)
                print("Ax object", action.tree_line)
                print("Trajectory: ", action.display_trajectory())
                if action.trajectory:
                    print("***Executing Trajectory***")
                for traj in action.trajectory:
                    apply_action(page, traj, page.screenshot(), traj.friendly_xpath)
                    wait_for_load(page, load_time_ms=3000)
                before_screenshot = page.screenshot()
                friendly_element = page.evaluate(
                    f"document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue")

                if friendly_element:
                    page.evaluate(
                        f"document.evaluate('{friendly_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.scrollIntoView();")
                else:
                    element = page.evaluate(
                        f"document.evaluate('{action.xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue")
                    if element:
                        page.evaluate(
                            f"document.evaluate('{action.xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.scrollIntoView();")
                    else:
                        print(f"Element not found for XPath: {action.xpath}, Ax object: {action.tree_line}")
                        continue
                action.set_friendly_xpath(friendly_xpath)
                apply_action(page, action, before_screenshot, friendly_xpath)
                wait_for_load(page, load_time_ms=3000)
                if len(page.context.pages) > 1 and page.context.pages[-1] != page:
                    new_page = page.context.pages[-1]
                    after_screenshot = new_page.screenshot(full_page=False)
                    with eq_class_lock:
                        eq_class.update_unique_actions([action], before_state.html, new_page.content(),
                                                       before_screenshot, after_screenshot)
                    with page_queue_lock:
                        with seen_urls_lock:
                            if normalize_url(new_page.url) not in seen_urls:
                                url_queue.put(new_page.url)
                                print(new_page.url)
                    new_page.close()
                else:
                    after_screenshot = page.screenshot(full_page=False)
                    with eq_class_lock:
                        eq_class.update_unique_actions([action], before_state.html, page.content(), # need to lock
                                                       before_screenshot, after_screenshot)
                
                #the url is being normalized a bit too aggressively to the point 
                #that pages that are clearly different are being put into the same eq 
                #because normalized url is the same
                # if normalize_url(before_state.url) != normalize_url(page.url):
                if before_state.url != page.url:
                    with page_queue_lock:
                        with seen_urls_lock:
                            if normalize_url(page.url) not in seen_urls:
                                url_queue.put(page.url)
                                print(page.url)
                else:
                    #since we stayed on the same page we want to see if applying
                    #this action generated new content on the page
                    try:
                        new_state = get_page_state(page, cdpSession)
                        new_actions = get_unique_actions(new_state)

                        #take the set difference unique_actions \ seen_actions
                        difference = [a for a in new_actions if not any(element_similarity(a.html, b.html) for b in seen_actions)]
                        #put the difference onto the queue
                        new_trajectory = []
                        if difference:
                            new_trajectory = cp.deepcopy(action.trajectory)
                            new_trajectory.append(action)
                            print("***Detected new actions***")
                        for different_action in difference:
                            print("New action: ", different_action.tree_line)
                            #update trajectory with parent's trajectory + parent
                            different_action.set_trajectory(new_trajectory)
                            action_queue.put(different_action)
                        #put the difference into the seen_actions, effectively unique_actions U seen_actions    
                        seen_actions += difference    
                    except Exception as e:
                        print(f"Error getting page state after applying {action.tree_line} at {url}. Error: {e}")
                        return
                page.goto(before_state.url)  # this threw an error once, idk why
                time.sleep(2)

        #NEED TO ACTUALLY UPDATE THE ACTIONS, THEY ARE ONLY ADDED AT THE BEGINNING - Cem


    explore_actions()
    if url_queue.empty() and url_queue.qsize() <= 0:
        idle_flags[thread_id] = True


def worker(thread_id: int, idle_flags: dict, url_queue: Queue, equiv_classes_lock: threading.Lock, eq_class_lock: threading.Lock, page_queue_lock: threading.Lock, seen_urls_lock: threading.Lock, equiv_classes: EquivalenceClassSet, seen_urls: set[str], headless: bool, cookies: Optional[dict], root: str, stop_event: threading.Event):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        page = context.new_page()
        cdpSession = context.new_cdp_session(page)

        if cookies is not None:
            context.add_cookies(cookies)

        while not stop_event.is_set():
            url = None
            try:
                url = url_queue.get(timeout=0.5)  # Reduced timeout value
            except Exception as e:
                idle_flags[thread_id] = True
                continue

            if url is not None:
                explore_page(url, equiv_classes_lock, eq_class_lock, page_queue_lock, seen_urls_lock, equiv_classes,
                             url_queue, seen_urls, page, cdpSession, root, thread_id, idle_flags)
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
    def save_equivalence_classes(equiv_classes: EquivalenceClassSet, output_dir: str):
        # Create the output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Save the screenshots separately and update the file paths
        for eq_class in equiv_classes.classes:
            for key, action_info in eq_class.unique_actions.items():
                before_screenshot_filename = f"action_{hash(key)}_before.png"
                before_screenshot_path = Path(output_dir) / before_screenshot_filename
                with open(before_screenshot_path, 'wb') as f:
                    f.write(action_info.before_screenshot)
                action_info.before_screenshot = str(before_screenshot_path)

                after_screenshot_filename = f"action_{hash(key)}_after.png"
                after_screenshot_path = Path(output_dir) / after_screenshot_filename
                with open(after_screenshot_path, 'wb') as f:
                    f.write(action_info.after_screenshot)
                action_info.after_screenshot = str(after_screenshot_path)

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

explore("https://www.dominos.com/en/", headless=False, root="dominos.com", num_threads=1)
