import time
from queue import Queue
import threading
from drivers import AxObservation
from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import pickle
from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from scrapecode.page_similarity import page_similarity
from scrapecode.element_similarity import element_similarity

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
class PageState:
    url: str
    html: str
    actions: list[Action]
    header_html: str
    footer_html: str


class EquivalenceClass:
    def __init__(self):
        self.lock = threading.Lock()
        self.page_urls = set()
        self.page_states: dict[str, PageState] = {}
        self.unique_actions: dict[str, ActionInfo] = {}

    def add_page(self, state: PageState):
        print('trying to add page inside eq class')
        with self.lock:
            print('trying to add page inside eq class2')
            normalized_url = normalize_url(state.url)
            self.page_urls.add(normalized_url)
            self.page_states[normalized_url] = state

    def update_unique_actions(self, actions: list[Action], before_html: str, after_html: str, before_screenshot: bytes, after_screenshot: bytes):
        with self.lock:
            for action in actions:
                action_key = action.html
                if action_key not in self.unique_actions or not self.has_similar_action(action):
                    self.unique_actions[action_key] = ActionInfo(action, before_html, after_html, before_screenshot, after_screenshot)

    def has_similar_action(self, action: Action) -> bool:
        with self.lock:
            return any(element_similarity(action.html, a.action.html) >= 0.9 for a in self.unique_actions.values())

    def is_new_action(self, action: Action) -> bool:
        with self.lock:
            return not self.has_similar_action(action)

    def is_similar(self, url: str, html: str) -> bool:
        with self.lock:
            normalized_url = normalize_url(url)
            if normalized_url in self.page_urls:
                return True

            for page_url in self.page_urls:
                if page_similarity(html, self.page_states[page_url].html) < 0.8:
                    return False

            return True


class EquivalenceClassSet:
    def __init__(self):
        self.lock = threading.Lock()
        self.classes: list[EquivalenceClass] = []
        self.added_urls: set[str] = set()
        self.common_actions = []

    def get_class(self, url: str, html: str) -> Optional[EquivalenceClass]:
        with self.lock:
            for eq_class in self.classes:
                with eq_class.lock:
                    if eq_class.is_similar(url, html):
                        return eq_class
            return None

    def add_page(self, state: PageState, eq_class: Optional[EquivalenceClass]) -> EquivalenceClass:
        print('trying to add apge inside equiv set')
        with self.lock:
            self.added_urls.add(normalize_url(state.url))
            print('trying to add apge inside equiv set2')
            if eq_class is None:
                eq_class = EquivalenceClass()
                self.classes.append(eq_class)
            print('trying to add apge inside equiv set3')
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

    xpath = ax_node["xpath"]
    html = ax_node["html"]
    role = ax_node["role"]

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        # Check if the action is a pure link in the header or footer
        if role.strip() == 'link' and (html in header_html or html in footer_html):
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
        elif role.strip() in input_roles:
            action = Action(Action.Type.INPUT, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return action

    return None


def apply_action(page: PlaywrightPage, a: Action) -> bool:
    match a.action_type:
        case Action.Type.CLICK_LINK | Action.Type.CLICK_IMPORTANT | Action.Type.CLICK_CHECKBOX | Action.Type.CLICK_RADIO:
            friendly_path = a.xpath if '(' in a.xpath.split("/")[0] else f"//{a.xpath}"
            try:
                page.evaluate(
                    f"() => {{ let e = document.evaluate('{friendly_path}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.scrollIntoViewIfNeeded(); e.click(); }}")
                return True
            except Exception as e:
                print(f"Error clicking element via javascript click: {e}")

            try:
                page.locator(f"xpath={friendly_path}").click()
                return True
            except Exception as e:
                print(f"Error clicking element via playwright xpath locator.click: {e}")

            return False

        case Action.Type.INPUT:
            # input_text = a.input_string
            input_text = "test"
            try:
                page.wait_for_load_state('networkidle')
                page.locator(f'xpath={a.xpath}').first.fill(input_text)
                page.wait_for_load_state('networkidle')
                if "search" in a.html:
                    # print("SEARCHING PRESS ENTER")
                    page.keyboard.press('Enter')
                    page.wait_for_load_state('networkidle')

            except Exception as e:
                print(f"Error inputting element: {e}")
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
    print("GETTING PAGE STATE")
    # Navigate to the given URL and wait for the page to load
    wait_for_load(page)

    # Retrieve the accessibility tree and create an AxObservation object
    cleaned = AxObservation(get_ax_tree(cdpSession), page.url)

    # Extract the header and footer HTML
    header_html = page.evaluate("document.getElementsByTagName('header')[0]?.outerHTML || ''")
    footer_html = page.evaluate("document.getElementById('navFooter')?.outerHTML || ''")
    # ABOVE IS AMAZON SPECIFIC, WE NEED TO FIGURE OUT HOW TO PIPELINE THIS!
    # I love Claude :)

    # Extract actions from the accessibility nodes and filter out None values
    actions = [ax_node_to_action(node, header_html, footer_html) for node in cleaned.nodes_info]
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
def explore_page(url: str, equiv_classes_lock: threading.Lock, new_pages_lock: threading.Lock, equiv_classes: EquivalenceClassSet, new_pages: list[str], seen_urls: set[str], page: PlaywrightPage, cdpSession: CDPSession, root: str):
    with new_pages_lock:
        if normalize_url(url) in seen_urls:
            print(f"Skipping already visited page: {url}")
            return
        seen_urls.add(normalize_url(url))

    if not url.startswith(root):
        print(f"Skipping page outside of root: {url}")
        return

    try:
        page.goto(url)
        wait_for_load(page)
    except Exception as e:
        print(f"Error navigating to page: {url}. Error: {e}")
        return

    def explore_actions():
        scrape_flag = False

        try:
            before_state = get_page_state(page, cdpSession)
        except Exception as e:
            print(f"Error getting page state: {url}. Error: {e}")
            return
        print(f"Got page state for {url}")
        with equiv_classes_lock:
            eq_class = equiv_classes.get_class(before_state.url, before_state.html)
            print("Got equivalence class")

        if eq_class is None:
            print("no eq class")
            scrape_flag = True
            with equiv_classes_lock:
                print('trying to add page to eq class')
                eq_class = equiv_classes.add_page(before_state, None) # this is fucking broken
            print("MADE eq class")
            with eq_class.lock:
                new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
            print("GOT ACTION!")
        else:
            print("found eq class")
            with eq_class.lock:
                new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
                if len(new_actions) > 0:
                    scrape_flag = True
                    equiv_classes.add_page(before_state, eq_class)
        print("TONK###")
        if scrape_flag:
            print('Exploring actions on page...')

            unique_actions = []
            for action in new_actions:
                if not any(element_similarity(action.html, a.html) >= 0.9 for a in unique_actions):
                    unique_actions.append(action)

            for action in unique_actions:
                if not action.xpath:
                    print(f"Skipping action without XPath: {action}")
                    continue

                friendly_xpath = action.xpath if '(' in action.xpath.split("/")[0] else f"//{action.xpath}"

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
                        print(f"Element not found for XPath: {action.xpath}")
                        continue

                time.sleep(0.5)
                before_screenshot = page.screenshot()

                apply_action(page, action)
                wait_for_load(page)

                time.sleep(0.5)
                if len(page.context.pages) > 1 and page.context.pages[-1] != page:
                    new_page = page.context.pages[-1]
                    after_screenshot = new_page.screenshot(full_page=False)
                    with eq_class.lock:
                        eq_class.update_unique_actions([action], before_state.html, new_page.content(),
                                                       before_screenshot, after_screenshot)
                    with new_pages_lock:
                        new_pages.append(new_page.url)
                    new_page.close()
                else:
                    after_screenshot = page.screenshot(full_page=False)
                    with eq_class.lock:
                        eq_class.update_unique_actions([action], before_state.html, page.content(),
                                                       before_screenshot, after_screenshot)

                if normalize_url(before_state.url) != normalize_url(page.url):
                    with new_pages_lock:
                        new_pages.append(page.url)
                    page.goto(before_state.url)

    explore_actions()


def worker(url_queue: Queue, equiv_classes_lock: threading.Lock, new_pages_lock: threading.Lock, equiv_classes: EquivalenceClassSet, new_pages: list[str], seen_urls: set[str], headless: bool, cookies: Optional[dict], root: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        page = context.new_page()
        cdpSession = context.new_cdp_session(page)

        if cookies is not None:
            context.add_cookies(cookies)

        while True:
            url = url_queue.get()
            if url is None:
                break
            explore_page(url, equiv_classes_lock, new_pages_lock, equiv_classes, new_pages, seen_urls, page, cdpSession, root)
            url_queue.task_done()

def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'scrape_amazon', root: str = "", num_threads: int = 4):
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
    new_pages_lock = threading.Lock()

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    seen_urls = set()
    new_pages = []

    url_queue = Queue()
    url_queue.put(starting_url)

    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker,
                             args=(url_queue, equiv_classes_lock, new_pages_lock, equiv_classes, new_pages, seen_urls, headless, cookies, root))
        t.start()
        threads.append(t)

    while True:
        print("TONK1")
        with new_pages_lock:
            while new_pages:
                print("TONK2")
                url = new_pages.pop(0)
                if normalize_url(url) not in seen_urls:
                    url_queue.put(url)
        if url_queue.empty():
            break
        time.sleep(1)

    for _ in range(num_threads):
        url_queue.put(None)

    for t in threads:
        t.join()

    save_equivalence_classes(equiv_classes, output_dir)

explore("https://us.supreme.com/pages/shop", headless=True, root="")