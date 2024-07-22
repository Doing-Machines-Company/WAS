from drivers import AxObservation
from action import Action

from playwright.sync_api import sync_playwright

from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from scrapecode.page_similarity import page_similarity
from utils.element_utils.element_similarity import element_similarity

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

@dataclass
class PageTransition:
    before_state: PageState
    action: Action
    after_state: PageState

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
            print("INPUTTING")
            print(a.xpath)
            input_text = a.input_string
            try:
                page.wait_for_load_state('networkidle')
                page.locator(f'xpath={a.xpath}').first.fill(input_text)
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


@dataclass
class PageObservation():
    raw_url: str
    url: str
    html: str
    raw_ax_tree: list[AxNode]
    ax_tree: AxObservation

    def hash(self):
        return self.url


class ObservationGraph:
    def __init__(self):
        self.nodes: dict[str, PageState] = {}
        self.edges: list[PageTransition] = []

    def add_node(self, state: PageState, eq_class: EquivalenceClass):
        url = normalize_url(state.url)
        if url not in self.nodes and eq_class.needs_scraping():
            self.nodes[url] = state

    def add_edge(self, transition: PageTransition):
        self.edges.append(transition)


def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(
        load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race


def explore(starting_url: str, cookies: Optional[dict] = None, headless: bool = False):
    equiv_classes = EquivalenceClassSet()
    graph = ObservationGraph()
    new_pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')

        page = context.new_page()
        cdpSession = context.new_cdp_session(page)

        if cookies is not None:
            context.add_cookies(cookies)

        def get_page_state(url):
            page.goto(url)
            wait_for_load(page)

            cleaned = AxObservation(get_ax_tree(cdpSession), url)
            actions = [ax_node_to_action(node) for node in cleaned.nodes_info]
            actions = [a for a in actions if a is not None]

            return PageState(
                url=normalize_url(page.url),
                html=page.content(),
                actions=actions,
                screenshot=page.screenshot()
            )

        def explore_page(url: str):
            state = get_page_state(url)

            eq_class = equiv_classes.add_page(state)
            graph.add_node(state, eq_class)

            for action in state.actions:
                before_html = state.html
                before_screenshot = state.screenshot

                apply_action(page, action)
                wait_for_load(page)

                after_state = get_page_state(page.url)

                transition = PageTransition(state, action, after_state)
                graph.add_edge(transition)

                if state.url != after_state.url:
                    new_pages.append(after_state.url)
                else:
                    eq_class.update_unique_actions([action], before_html, after_state.html, before_screenshot, after_state.screenshot)
                    new_actions = [a for a in after_state.actions if eq_class.has_new_action(a)]
                    for new_action in new_actions:
                        before_html = after_state.html
                        before_screenshot = after_state.screenshot

                        apply_action(page, new_action)
                        wait_for_load(page)

                        after_new_state = get_page_state(page.url)

                        new_transition = PageTransition(after_state, new_action, after_new_state)
                        graph.add_edge(new_transition)

                        eq_class.update_unique_actions([new_action], before_html, after_new_state.html, before_screenshot, after_new_state.screenshot)

                        if after_state.url != after_new_state.url:
                            new_pages.append(after_new_state.url)

                page.goto(state.url)
                wait_for_load(page)

        explore_page(starting_url)

        while new_pages:
            url = new_pages.pop(0)
            eq_class = equiv_classes.get_class(url, '')

            if eq_class is None or eq_class.needs_scraping():
                explore_page(url)
            else:
                state = get_page_state(url)

                for action_info in eq_class.unique_actions.values():
                    if eq_class.has_new_action(action_info.action):
                        before_html = state.html
                        before_screenshot = state.screenshot

                        apply_action(page, action_info.action)
                        wait_for_load(page)

                        after_state = get_page_state(page.url)

                        transition = PageTransition(state, action_info.action, after_state)
                        graph.add_edge(transition)

                        eq_class.update_unique_actions([action_info.action], before_html, after_state.html, before_screenshot, after_state.screenshot)

                        if state.url != after_state.url:
                            new_pages.append(after_state.url)

                page.goto(state.url)
                wait_for_load(page)

# explore("https://us.supreme.com/pages/shop")
explore("https://www.amazon.com/Brita-Filter-Pitcher-Standard-Without/dp/B09W4PLVQP/ref=sr_1_7?crid=3LCD2O3C4HNKO&dib=eyJ2IjoiMSJ9.XDFWvhkafbpG8bvke6HUJ1m7eZxOWDVPyhN0MM4tp6A4cF0UNkO2YR9ZtyNOPwzoqrhKHmWWbV5CJxzG_lRfHMy7Vu9fEwo2prr0asnohjrskeR_uMRTyEEIbN3DsS_6Lk-XDjigWxQVxqlDGGkd4MSDIPaU6nltNygG4URYkFf1b5Ib3p_3qlRvmELVRFo3-RxQ95GQVOW1jbYZErMvw5cv0OfHHHobJvcNrc-AgKKc8wXKTyJ4rW4b-FBLokmA23RnUPMO-yC4NJDvodqNabZ-AIbXrRh528W_Y-AwkwY.97zl7k14p0fVKq6Qbr7JmKMcgwchKGD8KgNIznoDwdQ&dib_tag=se&keywords=brita&qid=1709442919&sprefix=brita%2Caps%2C98&sr=8-7&th=1")