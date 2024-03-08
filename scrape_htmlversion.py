from drivers import AxObservation
from action import Action
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

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
    before_screenshot: bytes
    after_screenshot: bytes
@dataclass
class PageState:
    url: str
    html: str
    actions: list[Action]
    screenshot: bytes



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

    def has_new_action(self, action: Action) -> bool:
        return not self.has_similar_action(action)

    def is_similar(self, url: str, html: str) -> bool:
        normalized_url = normalize_url(url)
        if normalized_url in self.page_urls:
            return True

        for page_url in self.page_urls:
            if page_similarity(html, self.page_states[page_url].html) < 0.8:
                return False

        return True

    def needs_scraping(self) -> bool:
        return len(self.page_urls) < 10

class EquivalenceClassSet:
    def __init__(self):
        self.classes: list[EquivalenceClass] = []

    def get_class(self, url: str, html: str) -> Optional[EquivalenceClass]:
        for eq_class in self.classes:
            if eq_class.is_similar(url, html):
                return eq_class
        return None

    def add_page(self, state: PageState) -> EquivalenceClass:
        eq_class = self.get_class(state.url, state.html)
        if eq_class is None:
            print(f"Creating new equivalence class")
            eq_class = EquivalenceClass()
            self.classes.append(eq_class)
        else:
            print("Adding page to existing equivalence class")
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



            response = cdpSession.send(
                "DOM.getOuterHTML",
                {
                    "objectId": remote_object_id,
                },
            )
            node["html"] = response["outerHTML"]
        except Exception as e:
            if 'html' not in node:
                node['html'] = ''
            continue

    return accessibility_tree


def ax_node_to_action(ax_node: AxNode) -> Optional[Action]:
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
        'separator', 'toolbar', 'tooltip', 'presentation']

    input_roles = [
        'textbox', 'searchbox', 'slider', 'spinbutton', 'radiogroup',
        'checkbox', 'radio', 'switch', 'option', 'listbox',
        'combobox', 'textarea', 'spinbutton'
    ]
    # Error inputting element: Error: Element is not an <input>, <textarea> or [contenteditable] element

    # currently_ignored = ['gridcell', 'columnheader', 'rowheader', 'tab',
    #     'tabpanel', 'row', 'rowgroup', 'search', 'heading']

    html = ax_node["html"]
    role = ax_node["role"]

    if html and html.strip() != "":
        if role.strip() == 'link':
            return Action(Action.Type.CLICK_LINK, None, html)

        elif role.strip() in important_clickables:
            return Action(Action.Type.CLICK_IMPORTANT, None, html)

        elif role.strip() == 'radio':
            return Action(Action.Type.CLICK_RADIO, None, html)

        elif role.strip() == 'checkbox':
            return Action(Action.Type.CLICK_CHECKBOX, None, html)

        elif role.strip() in general_clickables:
            return Action(Action.Type.CLICK_GENERAL, None, html)

        elif role.strip() in input_roles:
            return Action(Action.Type.INPUT, None, html)

    return None


def apply_action(page: PlaywrightPage, a: Action) -> bool:
    match a.action_type:
        case Action.Type.CLICK_LINK | Action.Type.CLICK_IMPORTANT | Action.Type.CLICK_CHECKBOX | Action.Type.CLICK_RADIO:
            try:
                page.click(f"text={a.html}")
                return True
            except Exception as e:
                print(f"Error clicking element: {e}")

        case Action.Type.INPUT:
            print("INPUTTING")
            input_text = "test"
            try:
                page.wait_for_load_state('networkidle')
                page.fill(f"text={a.html}", input_text)
                page.wait_for_load_state('networkidle')
                if "search" in a.html:
                    print("SEARCHING PRESS ENTER")
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

        case Action.Type.GOTO_URL:
            page.goto(a.input_string)
            page.wait_for_load_state('networkidle')

        case Action.Type.GO_BACK:
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


@dataclass
class PageObservation():
    raw_url: str
    url: str
    html: str
    raw_ax_tree: list[AxNode]
    ax_tree: AxObservation

    def hash(self):
        return self.url




def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race


def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'scrape_trials'):
    # Initialize an EquivalenceClassSet to store and manage equivalence classes
    equiv_classes = EquivalenceClassSet()

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    def save_equivalence_classes(equiv_classes: EquivalenceClassSet, output_dir: str):
        data = {
            'classes': []
        }

        for eq_class in equiv_classes.classes:
            class_data = {
                'page_urls': list(eq_class.page_urls),
                'page_states': {},
                'unique_actions': {}
            }

            for url, state in eq_class.page_states.items():
                screenshot_filename = f"page_state_{hash(url)}.png"
                screenshot_path = Path(output_dir) / screenshot_filename
                with open(screenshot_path, 'wb') as f:
                    f.write(state.screenshot)

                class_data['page_states'][url] = {
                    'url': state.url,
                    'html': state.html,
                    'actions': [{'html': action.html} for action in state.actions],
                    'screenshot': screenshot_filename,
                }

            for key, action_info in eq_class.unique_actions.items():
                before_screenshot_filename = f"action_{hash(key)}_before.png"
                before_screenshot_path = Path(output_dir) / before_screenshot_filename
                with open(before_screenshot_path, 'wb') as f:
                    f.write(action_info.before_screenshot)

                after_screenshot_filename = f"action_{hash(key)}_after.png"
                after_screenshot_path = Path(output_dir) / after_screenshot_filename
                with open(after_screenshot_path, 'wb') as f:
                    f.write(action_info.after_screenshot)

                class_data['unique_actions'][key] = {
                    'action': {'html': action_info.action.html},
                    'before_html': action_info.before_html,
                    'after_html': action_info.after_html,
                    'before_screenshot': before_screenshot_filename,
                    'after_screenshot': after_screenshot_filename,
                }

            data['classes'].append(class_data)

        with open(Path(output_dir) / 'equivalence_classes.json', 'w') as f:
            json.dump(data, f, indent=2)

    # Initialize an empty list to store the URLs of new pages discovered during scraping
    new_pages = []

    # Use the sync_playwright context manager to launch a new browser instance
    with sync_playwright() as p:
        # Launch a new browser instance with the specified headless mode
        browser = p.chromium.launch(headless=headless)

        # Create a new browser context with a specific user agent
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')

        # Create a new page within the browser context
        page = context.new_page()

        # Establish a CDP (Chrome DevTools Protocol) session with the page
        cdpSession = context.new_cdp_session(page)

        # If cookies are provided, add them to the browser context
        if cookies is not None:
            context.add_cookies(cookies)

        # # Create a set of visited URLs so there is less looping, assumes visiting same URL, URL has no new actions
        # visited_urls = set()
        def get_page_state(url):
            # Navigate to the given URL and wait for the page to load
            page.goto(url)
            wait_for_load(page)

            # Retrieve the accessibility tree and create an AxObservation object
            cleaned = AxObservation(get_ax_tree(cdpSession), url)

            # IMPORTANT: ASSUMES THAT IF ACTION SOMEHOW DISAPPEARS WHILE SCRAPING SAME PAGE THAT IT IS NOT IMPORTANT

            # Extract actions from the accessibility nodes and filter out None values
            actions = [ax_node_to_action(node) for node in cleaned.nodes_info]
            actions = [a for a in actions if a is not None]

            # Create and return a PageState object with the normalized URL, HTML content, actions, and screenshot
            return PageState(
                url=normalize_url(page.url),
                html=page.content(),
                actions=actions,
                screenshot=page.screenshot()
            )

        def explore_page(url: str):

            state = get_page_state(url)

            # Add the page to the appropriate equivalence class and add the page state as a node to the observation graph
            eq_class = equiv_classes.add_page(state)

            def explore_actions(state: PageState, eq_class: EquivalenceClass):
                # Retrieve new actions that haven't been seen before in the equivalence class
                new_actions = [a for a in state.actions if eq_class.has_new_action(a)]
                # TODO continue converting from here

                # If there are new actions to explore
                if new_actions:
                    # Filter out similar actions to get a list of unique actions
                    unique_actions = []
                    for action in new_actions:
                        if not any(element_similarity(action.html, a.html) >= 0.9 for a in unique_actions):
                            unique_actions.append(action)

                    # For each unique action
                    for action in unique_actions:

                        # TODO, check if thing exists on the page

                        # TODO, Scroll to the element using HTML

                        # TODO, if doesn't exist, continue

                        before_html = state.html


                        # Take a screenshot before applying the action
                        before_screenshot = page.screenshot()

                        # Apply the action and wait for the page to load
                        apply_action(page, action)
                        wait_for_load(page)
                        # input("Press Enter to continue...")

                        # Get the page state after applying the action
                        after_state = get_page_state(page.url)

                        # Take a screenshot after the action without scrolling
                        after_screenshot = page.screenshot(full_page=False)

                        # Update the unique actions in the equivalence class with the before and after states
                        eq_class.update_unique_actions([action], before_html, after_state.html, before_screenshot,
                                                       after_screenshot)

                        # If the action leads to a new page (different URL), append it to the new_pages list for later exploration
                        if normalize_url(state.url) != normalize_url(after_state.url):
                            new_pages.append(after_state.url)
                        # If the action leads to the same page (same URL), recursively explore new actions on the same page
                        else:
                            explore_actions(after_state, eq_class)

            # Start exploring actions on the current page state and equivalence class
            explore_actions(state, eq_class)

        # Start the exploration process by exploring the starting URL
        explore_page(starting_url)

        # Continue exploring new pages until there are no more pages to explore
        while new_pages:
            print("Exploring new pages...")
            # Pop a URL from the new_pages list
            url = new_pages.pop(0)

            # Get the corresponding equivalence class for the URL
            eq_class = equiv_classes.get_class(url, '')

            # If the page doesn't belong to any existing equivalence class, explore the page
            if eq_class is None:
                explore_page(url)
            # If the page belongs to an existing equivalence class
            else:
                # Get the page state for the URL
                state = get_page_state(url)

                # Check for new actions that haven't been seen before in the equivalence class
                new_actions = [a for a in state.actions if eq_class.has_new_action(a)]

                # If there are new actions, explore the page and its actions
                if new_actions:
                    explore_page(url)
                # If there are no new actions, print a message indicating no new actions were found
                else:
                    print(f"No new actions found in equivalence class for page: {url}")

                # # Navigate back to the page state and wait for it to load
                # page.goto(state.url)
                # wait_for_load(page)
        save_equivalence_classes(equiv_classes, output_dir)

explore("https://us.supreme.com/pages/shop", headless=True)
# explore("https://www.amazon.com/Brita-Filter-Pitcher-Standard-Without/dp/B09W4PLVQP/ref=sr_1_7?crid=3LCD2O3C4HNKO&dib=eyJ2IjoiMSJ9.XDFWvhkafbpG8bvke6HUJ1m7eZxOWDVPyhN0MM4tp6A4cF0UNkO2YR9ZtyNOPwzoqrhKHmWWbV5CJxzG_lRfHMy7Vu9fEwo2prr0asnohjrskeR_uMRTyEEIbN3DsS_6Lk-XDjigWxQVxqlDGGkd4MSDIPaU6nltNygG4URYkFf1b5Ib3p_3qlRvmELVRFo3-RxQ95GQVOW1jbYZErMvw5cv0OfHHHobJvcNrc-AgKKc8wXKTyJ4rW4b-FBLokmA23RnUPMO-yC4NJDvodqNabZ-AIbXrRh528W_Y-AwkwY.97zl7k14p0fVKq6Qbr7JmKMcgwchKGD8KgNIznoDwdQ&dib_tag=se&keywords=brita&qid=1709442919&sprefix=brita%2Caps%2C98&sr=8-7&th=1")