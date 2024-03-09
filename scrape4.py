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

    def get_class(self, url: str, html: str) -> Optional[EquivalenceClass]:
        for eq_class in self.classes:
            if eq_class.is_similar(url, html):
                return eq_class
        return None

    def add_page(self, state: PageState, eq_class) -> EquivalenceClass:
        self.added_urls.add(normalize_url(state.url))
        # eq_class = self.get_class(state.url, state.html)
        if eq_class is None:
            # print(f"Creating new equivalence class")
            eq_class = EquivalenceClass()
            self.classes.append(eq_class)
        else:
            # print("Adding page to existing equivalence class")
            pass
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

    xpath = ax_node["xpath"]
    html = ax_node["html"]
    role = ax_node["role"]

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        if role.strip() == 'link':
            return Action(Action.Type.CLICK_LINK, xpath, html)

        elif role.strip() in important_clickables:
            # if 'Save with Used' in html:
            #     print(f"ROLE: {role}")
            #     print(f"HTML: {html}")
            #     print(f"XPATH: {xpath}")
            return Action(Action.Type.CLICK_IMPORTANT, xpath, html)

        elif role.strip() == 'radio':
            return Action(Action.Type.CLICK_RADIO, xpath, html)

        elif role.strip() == 'checkbox':
            return Action(Action.Type.CLICK_CHECKBOX, xpath, html)

        elif role.strip() in general_clickables:
            return Action(Action.Type.CLICK_GENERAL, xpath, html)

        elif role.strip() in input_roles:
            return Action(Action.Type.INPUT, xpath, html)

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






def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race


def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False, output_dir: str = 'scrape_trials', root: Optional[str] = ""):
    def save_equivalence_classes(equiv_classes: EquivalenceClassSet, output_dir: str):
        # Create the output directory if it doesn't exist
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Save the screenshots separately and update the file paths
        for eq_class in equiv_classes.classes:
            for key, action_info in eq_class.unique_actions.items():
                before_screenshot_filename = f"action_{hash(key)}_before.png"
                before_screenshot_path = Path(output_dir) / before_screenshot_filename
                with open(before_screenshot_path, 'wb') as f:
                    f.write(action_info.before_screenshot) # this is so jank, originally bytes, now str for pathing and ease of saving
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

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    seen_urls = set()


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
        def get_page_state():
            # Navigate to the given URL and wait for the page to load
            # page.goto(url) # TODO, perhaps not what you want
            wait_for_load(page)

            # Retrieve the accessibility tree and create an AxObservation object
            cleaned = AxObservation(get_ax_tree(cdpSession), page.url)

            # IMPORTANT: ASSUMES THAT IF ACTION SOMEHOW DISAPPEARS WHILE SCRAPING SAME PAGE THAT IT IS NOT IMPORTANT

            # Extract actions from the accessibility nodes and filter out None values
            actions = [ax_node_to_action(node) for node in cleaned.nodes_info]
            actions = [a for a in actions if a is not None]

            # Create and return a PageState object with the normalized URL, HTML content, actions, and screenshot
            return PageState(
                url=page.url,
                html=page.content(),
                actions=actions
            )

        def explore_page(url: str):
            # Normalize the URL
            # normalized_url = normalize_url(url)



            if normalize_url(url) in seen_urls:
                print(f"Skipping already visited page: {url}")
                return

            seen_urls.add(normalize_url(url))

            if not url.startswith(root):
                print(f"Skipping page outside of root: {url}")
                return

            page.goto(url)
            wait_for_load(page)

            def explore_actions():
                scrape_flag = False

                # Retrieve new actions that haven't been seen before in the equivalence class
                before_state = get_page_state() # URL not normalized



                eq_class = equiv_classes.get_class(before_state.url, before_state.html)

                if eq_class is None:
                    scrape_flag = True
                    eq_class = equiv_classes.add_page(before_state, eq_class)
                    new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
                    # eq_class = equiv_classes.add_page(before_state, eq_class)
                else:
                    new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
                    if len(new_actions) > 0:
                        scrape_flag = True
                        equiv_classes.add_page(before_state, eq_class)

                # If there are new actions to explore
                if scrape_flag:
                    print('Exploring actions on page...')
                    # Filter out similar actions to get a list of unique actions
                    # print('going')
                    unique_actions = []
                    for action in new_actions:
                        if not any(element_similarity(action.html, a.html) >= 0.9 for a in unique_actions): # may want to play around with this hyperparam
                            unique_actions.append(action)

                    # For each unique action
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
                                print(f"Element not found for XPath: {action.xpath}") # this happens a weirdly large amount of times
                                print(action.html)
                                continue

                        # Take a screenshot before applying the action
                        before_screenshot = page.screenshot()

                        # Apply the action and wait for the page to load
                        apply_action(page, action)
                        wait_for_load(page)
                        # input("Press Enter to continue...")

                        # Take a screenshot after the action without scrolling
                        after_screenshot = page.screenshot(full_page=False)
                        after_state = get_page_state()

                        # Update the unique actions in the equivalence class with the before and after states
                        eq_class.update_unique_actions([action], before_state.html, after_state.html, before_screenshot,
                                                       after_screenshot)


                        # If the action leads to a new page (different URL), append it to the new_pages list for later exploration
                        if normalize_url(before_state.url) != normalize_url(page.url):
                            new_pages.append(page.url) # perhaps stop adding new pages if already in new_pages
                            page.goto(before_state.url) # hopefully same XPATH means same HTML and same action
                            # TODO, CREATE AND EQUIVALENCE CLASS FOR THESE????

                        # If the action leads to the same page (same URL), recursively explore new actions on the same page
                        # explore_actions()  # TODO, maybe correct? Is NOT correct!
                        #
                        # break
                    # # TODO Something after going through a whole page
                    # after_scrape_state = get_page_state()  # URL not normalized
                    #
                    # eq_class = equiv_classes.get_class(after_scrape_state.url, after_scrape_state.html)
                    # assert(eq_class is not None)
                    # new_actions = [a for a in before_state.actions if eq_class.is_new_action(a)]
                    # if len(new_actions) > 0:
                    #     explore_actions()


            # Start exploring actions on the current page state and equivalence class
            explore_actions()

        # Start the exploration process by exploring the starting URL
        explore_page(starting_url)

        # Continue exploring new pages until there are no more pages to explore
        while new_pages: # new_pages is a list of strings which are urls
            print(new_pages)
            print(len(new_pages))
            # print("Exploring new pages...")
            # Pop a URL from the new_pages list
            url = new_pages.pop(0)
            explore_page(url)

        save_equivalence_classes(equiv_classes, output_dir)

explore("https://us.supreme.com/pages/shop", headless=True, root="https://us.supreme.com")
# explore("https://www.amazon.com/Brita-Filter-Pitcher-Standard-Without/dp/B09W4PLVQP/ref=sr_1_7?crid=3LCD2O3C4HNKO&dib=eyJ2IjoiMSJ9.XDFWvhkafbpG8bvke6HUJ1m7eZxOWDVPyhN0MM4tp6A4cF0UNkO2YR9ZtyNOPwzoqrhKHmWWbV5CJxzG_lRfHMy7Vu9fEwo2prr0asnohjrskeR_uMRTyEEIbN3DsS_6Lk-XDjigWxQVxqlDGGkd4MSDIPaU6nltNygG4URYkFf1b5Ib3p_3qlRvmELVRFo3-RxQ95GQVOW1jbYZErMvw5cv0OfHHHobJvcNrc-AgKKc8wXKTyJ4rW4b-FBLokmA23RnUPMO-yC4NJDvodqNabZ-AIbXrRh528W_Y-AwkwY.97zl7k14p0fVKq6Qbr7JmKMcgwchKGD8KgNIznoDwdQ&dib_tag=se&keywords=brita&qid=1709442919&sprefix=brita%2Caps%2C98&sr=8-7&th=1")