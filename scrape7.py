import time
from queue import Queue
import threading
from drivers import AxObservation
# from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Dialog, TimeoutError
import pickle
# from typing import Optional, Any
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
from classes import *
import urllib.parse
import shutil


"""
there are two relations -- 1. coarse relation 2. fine relation

1. coarse relation
two states relate if their urls normalize the same

2. fine relation
two states relate if their urls are the exact same or...
their actions match above a threshold

the need for the fine relation and explicit action matching has to do with the fact that normalizing is a coarse measure, and 
no method currently exists to properly normalize urls in a way that is consistent with the actions and content of different web pages.

instead, the coarse relation can narrow our search space when there is no exact url match to lessen usage of the computationally expensive action matches
"""
action_number = 1


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
            node["action_effect"] = None

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


def ax_node_to_action(ax_node: AxNode, header_html: str, footer_html: str, url: str) -> IndefiniteAction:

    possible_action_types = []

    important_clickables = [
        'button',
    ]

    general_clickables = [  # dialog clickable?
        'treeitem', 'switch', 'option', 'menuitemcheckbox',
        'menuitemradio',
        'slider', 'listbox', 'tree',
        'grid', 'alert', 'alertdialog',
        'log', 'marquee', 'timer', 'tooltip', 'banner',
        'complementary', 'contentinfo', 'form',
        'region', 'status', 'img', 'note', 'application',
        'cell', 'definition', 'directory', 'document',
        'feed', 'figure', 'group', 'img', 'list',
        'listitem',
        'option', 'tab']

    selects = [  # need menuitemcheckbox and menuitemradio? - JC
        'menuitem'
    ]

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
    ignored_roles = [
        'main',
        'article',
        'group',
        'dialog',
        'document',
        'navigation',
        'status',
        'alert',
        'complementary',
        'alertdialog',
        'grid'
    ]
    xpath = ax_node["xpath"]
    html = ax_node["html"]
    role = ax_node["role"]
    nodeId = ax_node["nodeId"]

    soup = BeautifulSoup(html, 'html.parser')

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        # Check if the action is a pure link in the header or footer
        if role.strip () in ignored_roles:
            return IndefiniteAction([], None, nodeId)  # may just want to return None?
        if html in footer_html or (html in header_html and url not in 'https://www.dominos.com/en/'):
            return IndefiniteAction([], None, nodeId)

        #not sure what this does at all - Cem
        if any(attr in html.lower() for attr in non_browser_attributes):
            return IndefiniteAction([], None, nodeId)

        if role.strip() == 'link':
            possible_action_types.append(Action.Type.CLICK_LINK)

        elif role.strip() in important_clickables:
            possible_action_types.append(Action.Type.CLICK_IMPORTANT)

        elif role.strip() == 'radio':
            # action = Action(Action.Type.CLICK_RADIO, xpath, html)
            # action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_RADIO)

        elif role.strip() == 'checkbox':
            possible_action_types.append(Action.Type.CLICK_CHECKBOX)

        elif role.strip() in general_clickables:
            # action = Action(Action.Type.CLICK_GENERAL, xpath, html)
            # action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_GENERAL)

        elif role.strip() in selects:
            possible_action_types.append(Action.Type.SELECT_GENERAL)

        elif role.strip() in input_roles or soup.find(('input', 'textarea')):

            # input_type = None
            #
            # input_element = soup.find('input')
            #
            # if input_element:
            #     input_type = input_element.get('type', '').lower()
            #
            # if input_type == 'checkbox' and Action.Type.CLICK_CHECKBOX not in possible_action_types:
            #     possible_action_types.append(Action.Type.CLICK_CHECKBOX)
            #
            # elif input_type == 'radio' and Action.Type.CLICK_RADIO not in possible_action_types:
            #     possible_action_types.append(Action.Type.CLICK_RADIO)
            #
            # else:
            possible_action_types.append(Action.Type.INPUT)


        elif soup.has_attr('contenteditable') and soup['contenteditable'].lower() == 'true':
            possible_action_types.append(Action.Type.INPUT)

    if possible_action_types != []:
        action = Action(None, xpath, html)
        action.set_tree_line(f"{role}: {ax_node['name']}")
        action.set_desired_option(ax_node['name'])
        # if xpath and xpath == "id(\"tab-Delivery\")":
        #     print("FOUND DELIVERY OPTION")
        #     print(possible_action_types)
        return IndefiniteAction(possible_action_types, action, nodeId)
    else:
        return IndefiniteAction([], None, nodeId)

def remove_last_xpath_item(xpath):
    # Split the string from the right at the last '/'
    parts = xpath.rsplit('/', 1)
    # If there is a '/' in the string, join the parts excluding the last part
    if len(parts) > 1:
        return parts[0]
    # If there is no '/', return the original string
    return xpath

def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None) -> (bool, Action):  # TODO handle multiple possible action types
    for a_type in possible_types:
        try:
            if a_type in [Action.Type.CLICK_LINK, Action.Type.CLICK_IMPORTANT, Action.Type.CLICK_CHECKBOX,
                               Action.Type.CLICK_RADIO, Action.Type.CLICK_GENERAL]:
                if playwright_element:
                    try:
                        page.evaluate(
                            f"() => {{ let e = document.evaluate('{found_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
                        a.action_type = a_type  # probs not good
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via JavaScript click: {e}")

                    try:
                        playwright_element.click(timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error clicking element via Playwright locator.click: {e}")

            elif a_type == Action.Type.SELECT_GENERAL:
                if playwright_element or found_xpath:
                    try:
                        page.evaluate(f"""
                                (xpath) => {{
                                    const option = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                    if (option) {{
                                        option.selected = true;
                                        const event = new Event('change', {{ bubbles: true }});
                                        option.parentElement.dispatchEvent(event);
                                    }}
                                }}
                            """, found_xpath)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error selecting element via Javascript: {e}")

                    try:
                        friendly_xpath = remove_last_xpath_item(found_xpath)  # overrides, may be broken after change which makes apply action use playwright objects
                        found_item = page.locator(f"xpath={friendly_xpath}")
                        found_item.select_option(a.desired_option.strip(), timeout=5000)
                    except Exception as e:
                        print(f"Error selecting element via Playwright and trimmed xpath: {e}")

            elif a_type == Action.Type.INPUT:
                if found_xpath:
                    try:
                        input_fill = use_gpt_fill_input('None', before_screenshot, a.html, True)
                        playwright_element.fill(input_fill, force=True, timeout=5000)
                        a.action_type = a_type
                        return True, a
                    except Exception as e:
                        print(f"Error inputting text into element: {e}")

            elif a_type == Action.Type.GOTO_URL:
                try:
                    page.goto(a.input_string, timeout=5000)
                    # page.wait_for_load_state('networkidle', timeout=5000)
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
    # parsed_url = urlparse(url)
    # scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    # netloc = parsed_url.netloc
    # path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment
    return url

def get_page_state(page: PlaywrightPage, cdpSession: CDPSession, attempts=3) -> PageState:

    result = None

    for _ in range(attempts):
        # Navigate to the given URL and wait for the page to load
        wait_for_load(page)

        # Retrieve the accessibility tree and create an AxObservation object
        ax_nodes = get_ax_tree(cdpSession)
        cleaned = AxObservation(ax_nodes, page.url)  # LITERALLY THE WHOLE TREE
        #DON'T PRINT FOR NOW, IT'S CLUTTERING EVERYTHING

        # Extract the header and footer HTML
        header_html = page.evaluate("document.getElementsByTagName('header')[0]?.outerHTML || ''")
        footer_html = page.evaluate("document.getElementsByTagName('footer')[0]?.outerHTML || ''")
        #currently page specific

        # Extract actions from the accessibility nodes and filter out None values, only scrape header and footer on homepage
        # actions = [ax_node_to_action(node, header_html if page.url not in 'https://www.dominos.com/en/' else '', footer_html if page.url not in 'https://www.dominos.com/en/' else '') for node in cleaned.nodes_info]
        '''
        
        IMPORTANT: ACTIONS FROM CLEANED AND NOT RAW AX_NODES!!!
        SO EVERYTHING ACTUALLY IS IN VIEWABLE TREE!!!
        
        '''

        indefinite_actions = [ax_node_to_action(node, header_html, footer_html, page.url) for node in cleaned.nodes_info]

        new_indefinite_actions = []
        for indefinite_action in indefinite_actions:
            if indefinite_action.action is not None and indefinite_action.type_list != []:
                new_indefinite_actions.append(indefinite_action)
        # indefinite_actions = [(tL, a) for (tL, a) in indefinite_actions if tL != []]  # TODO now a list of lists of actions


        # Create and return a PageState object with the normalized URL, HTML content, actions, header HTML, and footer HTML

        result = PageState(
            url=page.url,
            ax_nodes=cleaned.nodes_info,  # note now this nodes info is the cleaned version of nodes that we get out of AxObservation
            html=page.content(),
            actions=new_indefinite_actions,
            header_html=header_html,
            footer_html=footer_html
        )

        if len(result.actions) > 0:
            return result

    return result

def create_new_context_and_page(browser, cookies):
        context = browser.new_context(
            permissions=[], #this is to prevent popups
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        if cookies is not None:
            context.add_cookies(cookies)
        page = context.new_page()
        cdpSession = context.new_cdp_session(page)
        return context, page, cdpSession
def login(page):
    # print('LOGGING IN')
    page.goto('https://www.dominos.com/en/restaurants?type=Delivery')
    wait_for_load(page)
    page.get_by_label("Street Address", exact=False).fill('5819 Centre Ave')
    page.get_by_label("Suite/Apt #", exact=False).fill('Apt 448')
    page.get_by_label("ZIP Code", exact=False).fill('15206')
    page.get_by_label("City", exact=False).fill('Pittsburgh')
    page.get_by_label("State", exact=False).select_option('PA')  # THIS
    page.get_by_role("button", name="Continue for Delivery").click()
    wait_for_load(page)
    page.get_by_role("button", name="Delivery To").click()
    page.get_by_role("button", name="Change").click()
    page.get_by_role("button", name="Carryout").click()
    page.get_by_role("button", name="Continue").click()
    wait_for_load(page)
def setup_context(browser, cookies, logged_in = True, attempts = 3):
    context, page, cdpSession = create_new_context_and_page(browser, cookies)
    success = True
    if logged_in:
        for attempt in range(attempts):
            try:
                if not success: #if we failed before, create new context and page
                    context, page, cdpSession = create_new_context_and_page(browser, cookies)
                    print("Trying login again...")
                login(page)
                # print('LOGIN SUCCESSFUL')
            except Exception as e:
                # page.screenshot(path='login_failure.png', full_page=True)
                cdpSession.detach()
                page.close()
                context.close()
                print(f"Error logging in {attempt+1} times: {e}")
                success=False
            else:
                success = True
                break
    return context, page, cdpSession, success
def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race
def explore_page(url: str, equiv_classes_lock: threading.Lock, eq_class_lock: threading.Lock,
                 page_queue_lock: threading.Lock,
                 seen_urls_lock: threading.Lock, equiv_classes: URLStateManager, url_queue: Queue, seen_urls: set[str],
                 browser, cookies, root: str, thread_id: int, idle_flags: dict):

    # context = browser.new_context(
    #     user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
    # page = context.new_page()  # instead of making page here, make page in explore_page
    # cdpSession = context.new_cdp_session(page)
    #
    # if cookies is not None:
    #     context.add_cookies(cookies)

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
    def get_unique_actions(new_state: PageState) -> list[list[IndefiniteAction]]:
        sample_size = 2 #maximum number of samples to include among similar actions
        unique_actions = []
        new_actions = new_state.actions
        header_html = new_state.header_html
        footer_html = new_state.footer_html
        for indefinite_action in new_actions:
            action = indefinite_action.action
            if action.html in header_html or action.html in footer_html:
                unique_actions.append([indefinite_action]) #add header/footer items to own sample
            else:
                unique = True
                for samples in unique_actions:
                    if any(element_similarity(action.html, sample_indefinite_action.action.html) >= 0.9 for sample_indefinite_action in samples):
                        #  Perhaps add to best match and not first one >= 0.9?
                        if len(samples) < sample_size:
                            samples.append(indefinite_action)
                        unique = False
                        break
                if unique:
                    unique_actions.append([indefinite_action])
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

    def take_screenshot(page, attempts=3, full=False):
        for i in range(attempts):
            try:
                screenshot = page.screenshot(full_page=full)
                return screenshot, True
            except Exception as e:
                print("SCREENSHOT FAILED")
                print(e)
        print("ALL SCREENSHOT ATTEMPTS FAILED")
        # Create a blank image using OpenCV
        height, width = 600, 800  # You can adjust these dimensions as needed
        blank_image = np.zeros((height, width, 3), np.uint8)
        blank_image[:] = (255, 255, 255)  # White background

        # Add text to the image
        font = cv2.FONT_HERSHEY_SIMPLEX
        text = "Screenshot Failed"
        textsize = cv2.getTextSize(text, font, 1, 2)[0]
        text_x = (width - textsize[0]) // 2
        text_y = (height + textsize[1]) // 2
        cv2.putText(blank_image, text, (text_x, text_y), font, 1, (0, 0, 0), 2)

        # Convert the OpenCV image to bytes (similar to Playwright's screenshot output)
        _, buffer = cv2.imencode('.png', blank_image)
        print("SAVING DUMMY SCREENSHOT")
        return buffer.tobytes(), False

    def make_xpath_friendly(des_xpath):
        if des_xpath:  # if not empty string and not none
            return des_xpath if '(' in des_xpath.split("/")[0] else f"//{des_xpath}"
        else:
            return None

    def get_element(des_page, des_xpath):
        return des_page.locator(f"xpath={des_xpath}") if des_xpath else None
        # if des_xpath:
        #     return des_page.evaluate(
        #         f"document.evaluate('{des_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue")
        # else:
        #     return None


    def scroll_into_view(playwright_element):
        playwright_element.scroll_into_view_if_needed(timeout=10000)



    def explore_actions():
        context, page, cdpSession, login_success = setup_context(browser, cookies)
        if not login_success:
            print("LOGIN FAILED")
            return
        try:
            page.goto(url)
            wait_for_load(page, load_time_ms=3000)
        except Exception as e:
            print(f"Error navigating to page: {url}. Error: {e}")
            return

        print("*" * 80)
        print("Exploring ", url)

        try:
            root_state = get_page_state(page, cdpSession)
        except Exception as e:
            print(f"Error getting page state: {url}. Error: {e}")
            return
        # REMEMBER TO HANDLE EQUIVALENCE CLASS CODE - CEM !!!!
        #remember to add a lock
        with equiv_classes_lock:
            url_state = equiv_classes.get_state(root_state)
            if url_state is None:
                url_state = URLState(url) #initialize an empty URLState
                equiv_classes.add_url(url, url_state) #also add a direct link
            else:
                url_state.add_alias(url) #add this url as an alias to the matched state
                equiv_classes.add_url(url, url_state) #also add a direct link
                print(url, " is an alias for ", url_state.aliases)
                cdpSession.detach() #don't forget to close session!
                page.close()
                context.close()
                return #no longer want to scrape the page

        # seen_actions = []
        #data structure to control flow of new actions
        action_queue = Queue()

        unique_actions = get_unique_actions(root_state)  # should check typing, list of lists of indefinite actions

        #at this point, seen_actions is empty, so we can just put the unique actions into the queue
        for samples in unique_actions:
            action_queue.put(samples)
        #we can just set seen_actions since it is empty
        #TO IMPROVE EFFICIENCY MAYBE JUST SET THIS TO STRICTLY UNIQUE  - CEM
        #used to check whether an action has already been queued yet (if seen again, we shouldn't requeue)
        seen_actions = unique_actions  # Now a list of IndefiniteAction(s)
        while action_queue.qsize() > 0:
            samples = action_queue.get(timeout=0.5)  # possible_types should have some sort of importance ordering
            #  a samples is a list of indefinite actions
            sample_action_infos : list[ScrapeAction] = []
            for indefinite_sample in samples:

                possible_types = indefinite_sample.type_list
                action = indefinite_sample.action

                if not action.xpath:
                    print(f"Skipping action without XPath: {action}")
                    continue

                page.evaluate("""
                    window.print = function() {
                        console.log('Print was triggered');
                    };
                """)


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
                        possible_types_traj = [traj_action.action_type]

                        traj_element = get_element(page, traj_action.xpath)
                        assert(traj_action.friendly_xpath != None)
                        traj_xpath = traj_action.xpath
                        if not traj_element or traj_element.evaluate(
                                "element => element.outerHTML") != traj_action.html:  # perhaps do a stripped check
                            traj_element = get_element(page, traj_action.friendly_xpath)
                            traj_xpath = traj_action.friendly_xpath
                            if not traj_element or traj_element.evaluate(
                                    "element => element.outerHTML") != traj_action.html:
                                # now we try getting stuff at rune time
                                potentially_better_traj_xpath = get_xpath_by_outer_html(page, traj_action.html)
                                potentially_better_friendly_traj_xpath = make_xpath_friendly(potentially_better_traj_xpath)
                                traj_element = get_element(page, potentially_better_friendly_traj_xpath)
                                traj_xpath = potentially_better_friendly_traj_xpath
                                if not traj_element:
                                    traj_element = get_element(page, potentially_better_traj_xpath)
                                    traj_xpath = potentially_better_traj_xpath
                                    if not traj_element:
                                        traj_element = get_element(page, traj_action.friendly_xpath)
                                        traj_xpath = traj_action.friendly_xpath
                                        if not traj_element:
                                            traj_element = get_element(page, traj_action.xpath)
                                            traj_xpath = traj_action.xpath

                        # element = get_element(page, backup_xpath)
                        # found_xpath = backup_xpath
                        # if not element:
                        #     found_xpath = backup_xpath
                        #     element = get_element(page, make_xpath_friendly(backup_xpath))
                        # # backup_friendly_xpath = backup_xpath if '(' in backup_xpath.split("/")[0] else f"//{backup_xpath}"
                        # if not element:
                        #     found_xpath = action.friendly_xpath
                        #     element = get_element(page, action.friendly_xpath)
                        # if not element:
                        #     found_xpath = action.xpath
                        #     element = get_element(page, action.xpath)
                        if traj_element and traj_xpath:
                            try:
                                scroll_into_view(traj_element)
                            except Exception as e:
                                print("SCROLL FAILED DURING TRAJECTORY")
                                print(e)
                            trajectory_action_screenshot, _ = take_screenshot(page)
                            success, _ = apply_action(page, traj_action, trajectory_action_screenshot, traj_element, traj_xpath, possible_types_traj)
                            if not success:
                                print("Trajectory broken, skipping")
                                traj_success = False
                                break
                        else:
                            print('Could not find item in trajectory')
                            traj_success = False
                            break
                        wait_for_load(page, load_time_ms=3000)
                    wait_for_load(page, load_time_ms=3000)
                    print("***Finished Executing Trajectory***")
                if not traj_success:
                    continue

                action.set_friendly_xpath(make_xpath_friendly(action.xpath))

                scroll_success = False

                #  May want to deepcopy action for safety here


                final_element = get_element(page, action.xpath)
                final_xpath = action.xpath
                if not final_element or final_element.count() < 1 or final_element.evaluate("element => element.outerHTML") != action.html:  # perhaps do a stripped check
                    final_element = get_element(page, action.friendly_xpath)
                    final_xpath = action.friendly_xpath
                    if not final_element or final_element.count() < 1 or final_element.evaluate("element => element.outerHTML") != action.html:
                        # now we try getting stuff at rune time
                        potentially_better_xpath = get_xpath_by_outer_html(page, action.html)
                        potentially_better_friendly_xpath = make_xpath_friendly(potentially_better_xpath)
                        final_element = get_element(page, potentially_better_friendly_xpath)
                        final_xpath = potentially_better_friendly_xpath
                        if not final_element:
                            final_element = get_element(page, potentially_better_xpath)
                            final_xpath = potentially_better_xpath
                            if not final_element:
                                final_element = get_element(page, action.friendly_xpath)
                                final_xpath = action.friendly_xpath
                                if not final_element:
                                    final_element = get_element(page, action.xpath)
                                    final_xpath = action.xpath

                if final_element and final_element.count() > 0:
                    action.set_xpath(final_xpath)
                    try:
                        scroll_into_view(final_element)
                        scroll_success = True
                    except Exception as e:
                        print(f'Scroll failed: {e}')

                if not scroll_success:  # now is scroll failed for one scroll but you have an element, assume scroll will always fail, as locator should be the same
                    print(f"Scroll failed for: {final_xpath}, Ax object: {action.tree_line}, outerHTML: {action.html}")
                        # we may still want to try action even if scroll fails throwing playwright error to cause exception, though this is likely due to locator and it's broken
                if not final_element or final_element.count() < 1:
                    print("Element not found, continuing")
                    continue

                to_box_coords = None
                try:
                    # to_box_item = page.locator(f"xpath={action.friendly_xpath}")
                    if final_element:
                        to_box_coords = final_element.bounding_box(timeout=10000)
                except Exception as e:
                    print(f'GETTING BOUNDING BOXES FAILED FOR {action}')
                    print(e)
                before_screenshot, screenshot_success = take_screenshot(page)
                if screenshot_success:
                    before_screenshot = create_boundingbox(before_screenshot, to_box_coords)
                else:
                    print("NO SCREENSHOT AVAILABLE FOR BOUNDING BOX")
                # print(type(before_screenshot))
                before_state = get_page_state(page, cdpSession)
                success, new_action = apply_action(page, action, before_screenshot, final_element, final_xpath, possible_types)
                # action = new_action  # There may have been an aliasing issue here
                if not success:
                    print(f"This action was not successful: {action}")
                    print(f"Attempted types: {possible_types}")
                    continue  # hopefully no issues with this

                    # print("THIS ACTION SUCCESSFUL")
                # print(action)

                wait_for_load(page, load_time_ms=3000)
                if len(page.context.pages) > 1 and page.context.pages[-1] != page:
                    new_page = page.context.pages[-1]
                    after_screenshot, _ = take_screenshot(page)
                    # after_screenshot = new_page.screenshot(full_page=False)
                    sample_action_infos.append(ScrapeAction(action, before_state.html, new_page.content(), before_screenshot, after_screenshot, url, None))
                    with page_queue_lock:
                        with seen_urls_lock:
                            if normalize_url(new_page.url) not in seen_urls and root_state.url != page.url:
                                # REMEMBER TO ADD BACK THIS LINE IMMEDIATELY
                                url_queue.put(new_page.url)  # Adds stuff to be scraped
                                #  Make sure everything is discovered, unknown unknowns

                                print(new_page.url)
                    new_page.close()
                else:
                    after_screenshot, _ = take_screenshot(page)
                    # after_screenshot = page.screenshot(full_page=False)
                    sample_action_infos.append(ScrapeAction(action, before_state.html, page.content(), before_screenshot, after_screenshot, url, None))


                #the url is being normalized a bit too aggressively to the point
                #that pages that are clearly different are being put into the same eq
                #because normalized url is the same
                # if normalize_url(before_state.url) != normalize_url(page.url):
                if root_state.url != page.url:
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
                        # for sample1 in new_actions:
                        #     print("New sample")
                        #     for action1 in sample1:
                        #         print(action1[1].tree_line)
                        #         for seen_sample1 in seen_actions:
                        #             if element_similarity(action1[1].html, seen_sample1[0][1].html) >= .9:
                        #                 print("\t *** Matches to")
                        #                 print("\t ", seen_sample1[0][1].tree_line)
                        #take the set difference unique_actions \ seen_actions
                        #it is fine to just compare one action from each sample, since we assume transitive similarity
                        # seen_actions is all samples, a list of lists of indefinite actions
                        # a seen_sample is a list of indefinite actions
                        difference = [sample for sample in new_actions if all(element_similarity(sample[0].action.html, seen_sample[0].action.html) < .9 for seen_sample in seen_actions)]
                        #put the difference onto the queue
                        new_trajectory = []
                        if difference:
                            new_trajectory = cp.deepcopy(action.trajectory)
                            new_trajectory.append(action)
                            print("***Detected new actions***")
                        for sample in difference:  # each sample is a list of indefinite actions
                            print("New sample")
                            # for dTl, different_action in sample:
                            for indefinite_action in sample:
                                print("\tNew action: ", indefinite_action.action.tree_line)
                                #update trajectory with parent's trajectory + parent
                                indefinite_action.action.set_trajectory(new_trajectory)
                            action_queue.put(sample)
                        #put the difference into the seen_actions, effectively unique_actions U seen_actions
                        seen_actions += difference
                    except Exception as e:
                        print(f"Error getting page state after applying {action.tree_line} at {url}. Error: {e}")
                        return
                cdpSession.detach()
                page.close()
                context.close()

                context, page, cdpSession, login_success = setup_context(browser, cookies)

                # do_login(page)  # this should be the only other do_login we need hopefully
                if not login_success:
                    print("LOGIN FAILED")
                    continue

                page.goto(root_state.url)  # this threw an error once, idk why
                time.sleep(2)
            if sample_action_infos: #the only reason sample_action_infos may be empty is if the action errored out and never got added
                global action_number
                with eq_class_lock:
                    if url_state.add_sample(sample_action_infos): #proceed if this is a new action
                        #folder saving code
                        output_dir = 'dominos'
                        action_info = sample_action_infos[0]
                        tree_string = action_info.action.tree_line
                        tree_string = tree_string if len(tree_string) <= 40 else tree_string[:40]
                        cleaned_url = re.sub(r'^(https?://)?(www\.)?', '', action_info.url)
                        cleaned_url = cleaned_url.rstrip('/')
                        sample_path = Path (output_dir) / Path(urllib.parse.quote(cleaned_url, safe='')) / Path(str(action_number) + ' ' + tree_string) # root / url / action, make new url folder if it doesn't exist
                        sample_path.mkdir(parents = True, exist_ok = True)
                        for num, action_info in enumerate(sample_action_infos):
                            tree_string = action_info.action.tree_line
                            tree_string = tree_string if len(tree_string) <= 40 else tree_string[:40]
                            subdir_path = sample_path / Path(str(num))
                            subdir_path.mkdir(parents = True, exist_ok = True)
                            before_screenshot_filename = f"action_{hash(action_info.action.html)}_before.png"
                            before_screenshot_path = subdir_path / before_screenshot_filename
                            with open(before_screenshot_path, 'wb') as f:
                                f.write(action_info.before_screenshot)
                            action_info.before_screenshot = str(before_screenshot_path)

                            after_screenshot_filename = f"action_{hash(action_info.action.html)}_after.png"
                            after_screenshot_path = subdir_path / after_screenshot_filename
                            with open(after_screenshot_path, 'wb') as f:
                                f.write(action_info.after_screenshot)
                            action_info.after_screenshot = str(after_screenshot_path)

                            with open(Path(subdir_path) / 'info.txt', 'w') as f:
                                f.write(f"URL: {action_info.url}\n")
                                f.write(f"TREE LINE: {action_info.action.tree_line}\n")
                                f.write(f"XPATH: {action_info.action.friendly_xpath}\n")
                                f.write(f"TRAJECTORY: {action_info.action.trajectory}\n\n")
                                f.write(f"HTML: {action_info.action.html}\n")
                action_number +=1
        #  finally close here, make sure session is still attached
        if login_success:
            cdpSession.detach()
            page.close()
            context.close()
        #remove this, only here for testing


        #NEED TO ACTUALLY UPDATE THE ACTIONS, THEY ARE ONLY ADDED AT THE BEGINNING - Cem


    explore_actions()
    output_dir = 'dominos'
    output_path = Path(output_dir) / 'scraper_state.pkl'
    checkpoint_path = Path(output_dir) / 'checkpoint.pkl'
    urls = list(url_queue.queue)
    with open(output_path, 'wb') as f:
        pickle.dump(equiv_classes, f) #url_queue and current url needed for resume purposes
    with open(checkpoint_path, 'wb') as f:
        pickle.dump((action_number, urls, seen_urls), f)
    print("Saved checkpoint")
    if url_queue.empty() and url_queue.qsize() <= 0:
        idle_flags[thread_id] = True


def worker(thread_id: int, idle_flags: dict, url_queue: Queue, equiv_classes_lock: threading.Lock, eq_class_lock: threading.Lock, page_queue_lock: threading.Lock, seen_urls_lock: threading.Lock, equiv_classes, seen_urls: set[str], headless: bool, cookies: Optional[dict], root: str, stop_event: threading.Event):
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

def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'dominos', root: str = "", num_threads: int = 10, resume = False):
    global action_number
    # Initialize an EquivalenceClassSet to store and manage equivalence classes
    scraper_state_path = output_dir + '/' + 'scraper_state.pkl'
    checkpoint_path = output_dir + '/' + 'checkpoint.pkl'
    if resume and os.path.exists(scraper_state_path) and os.path.exists(checkpoint_path):
        with open(scraper_state_path, 'rb') as f:
            equiv_classes= pickle.load(f)
        with open(checkpoint_path, 'rb') as f:
            resumed_action_number, urls, seen_urls = pickle.load(f)
        action_number = resumed_action_number
        url_queue = Queue()
        for url in urls:
            url_queue.put(url)
        #remove partially filled urlstate 
        cleaned_url = re.sub(r'^(https?://)?(www\.)?', '', urls[0])
        cleaned_url = cleaned_url.rstrip('/')
        old_urlstate_path = output_dir + '/' + urllib.parse.quote(cleaned_url, safe='')
        if os.path.exists(old_urlstate_path):
            shutil.rmtree(old_urlstate_path)
            print("Removed partially explored urlstate")
        print("Resuming exploration from ", urls[0])
    else:
        if resume:
            print("Couldn't find checkpoint and state files for resume. Starting from scratch")
        equiv_classes : URLStateManager = URLStateManager()

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        seen_urls = set()

        url_queue = Queue()
        url_queue.put(starting_url)

    equiv_classes_lock = threading.Lock()
    eq_class_lock = threading.Lock()
    stop_event = threading.Event()
    page_queue_lock = threading.Lock()
    seen_urls_lock = threading.Lock()

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

    # Save the EquivalenceClassSet object using pickling

    print(url_queue.qsize())
    print(seen_urls)

# num_cores = os.cpu_count()

explore("https://www.dominos.com", headless=True, root="www.dominos.com", num_threads=1, resume = True)