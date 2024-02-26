from drivers import AxObservation
from action import Action

from playwright.sync_api import sync_playwright

from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

PlaywrightPage = Any
CDPSession = Any
AxNode = Any # TODO: make this a dataclass

def get_ax_tree(cdpSession : CDPSession) -> list[AxNode]:
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
            remote_object_id = remote_object["object"]["objectId"] # MAY BE ABLE TO FIND ELEMENT GIVEN REMOTE OBJECT ID, NO NEED FOR XPATHS
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
                    "objectId" : remote_object_id,
                },
            )
            node["html"]=response["outerHTML"]
            node["xpath"] = node_xpath
        except Exception as e:
            node['xpath'] = ''
            if 'html' not in node:
                node['html'] = ''
            continue
    
    return accessibility_tree

def ax_node_to_action(ax_node : AxNode) -> Optional[Action]:
    important_clickables = [
        'button',
    ]

    general_clickables = [
        'menuitem',
         'treeitem', 'switch', 'option', 'menuitemcheckbox',
        'menuitemradio',
        'slider', 'listbox', 'tree',
        'grid',  'alert', 'alertdialog', 'dialog',
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

def apply_action(page: PlaywrightPage, a : Action) -> bool:
    match a.action_type:
        case Action.Type.CLICK_LINK | Action.Type.CLICK_IMPORTANT | Action.Type.CLICK_CHECKBOX | Action.Type.CLICK_RADIO:
            friendly_path = a.xpath if '(' in a.xpath.split("/")[0] else f"//{a.xpath}"

            try:
                page.evaluate(f"() => {{ let e = document.evaluate('{friendly_path}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.scrollIntoViewIfNeeded(); e.click(); }}")
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

        case Action.Type.GOTO_URL: # haven't tested
            page.goto(a.input_string)
            page.wait_for_load_state('networkidle')

        case Action.Type.GO_BACK:
            # self.page.go_back() not actually using go_back as occasionally the last page is not useful, need to make better this is jank
            page.goto(a.input_string)
            page.wait_for_load_state('networkidle')
        
    return True

# this is the aggressive normalization
def normalize_url(url : str) -> str:
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment

@dataclass
class PageObservation():
    url: str
    html: str
    raw_ax_tree: list[AxNode]
    ax_tree: AxObservation

    def hash(self):
        return self.url

class ObservationGraph():

    def __init__(self):
        self.nodes = {}
        return
    
    def add_node(self, n : PageObservation):
        h = n.hash()
        assert not h in self.nodes
        self.nodes[h] = n
    
    def has_node(self, n : PageObservation):
        return n.hash() in self.nodes

    def has_node_hash(self, hash : str) -> bool:
        return hash in self.nodes

    def add_edge(self, from_page : PageObservation, action : Action, to_page : PageObservation):
        pass

def wait_for_load(page : PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(load_time_ms) # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race

def explore(starting_url : str, cookies : Optional[dict] = None, headless : bool = False):
    assert normalize_url(starting_url) == starting_url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.114 Safari/537.36')
        
        page = context.new_page()
        cdpSession = context.new_cdp_session(page)  # talk to chrome devtools

        if cookies is not None:
            context.add_cookies(cookies)

        G = ObservationGraph()

        page.goto(starting_url)
        wait_for_load(page)

        def explore_page() -> Optional[PageObservation]:
            url = normalize_url(page.url)
            visited = G.has_node_hash(url)

            # if not url.startswith(starting_url):
            #     print(f"Ignoring page {url} which doesn't start with {starting_url}.")
            #     return None

            print(f"{'Exploring' if not visited else 'Observing'} page {url}...")

            n = PageObservation(
                url=url,
                html=page.content(),
                raw_ax_tree=(raw := get_ax_tree(cdpSession)),
                ax_tree=(cleaned := AxObservation(raw, url))
            )
            if visited: return n

            G.add_node(n)

            page_actions = [ a for node in cleaned.nodes_info if (a := ax_node_to_action(node)) is not None ]

            print(f"Found {len(page_actions)} actions on {url}")

            for action in page_actions:
                if page.url != url:
                    page.goto(url)
                    wait_for_load(page)

                print(f"Applying action {action} on {url}...")

                if "null" in action.xpath:
                    print(action.html)

                apply_action(page, action)
                wait_for_load(page)

                n2 = explore_page()
                if n2 is None: continue

                # TODO: infer action effects here

                G.add_edge(n, action, n2)

            return n
        
        explore_page()

explore("https://us.supreme.com/pages/shop")