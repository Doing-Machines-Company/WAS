import time

from drivers import AxObservation
from action import Action # FIXME: where do we get Action from
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import pickle
from typing import Optional, Any
from time import sleep
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from scrapecode.page_similarity import page_similarity
from utils.element_utils.element_similarity import element_similarity
from bs4 import BeautifulSoup
import re
import os
import anthropic
import copy

api_key = os.getenv('ANTHROPIC_API_KEY')

anthropic_client = anthropic.Anthropic(
    api_key=api_key,
)


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
    ordered_candidates: list[str]

@dataclass
class PageState:
    url: str
    html: str
    actions: list[Action]
    chunks: list[(int, int, str)]
    obs: AxObservation


class EquivalenceClass:
    def __init__(self):
        self.page_urls = set()
        self.page_states: dict[str, PageState] = {}
        self.unique_actions: dict[str, ActionInfo] = {}
        self.chunks: list[Chunk] = []
        # self.noted_divs = dict()  # New addition for storing div information
        # removed noted_divs, not needed bc models are not being used

    def add_page(self, state: PageState):
        normalized_url = normalize_url(state.url)
        self.page_urls.add(normalized_url)
        self.page_states[normalized_url] = state

    def update_unique_actions(self, actions: list[Action], before_html: str, after_html: str, before_screenshot: bytes,
                              after_screenshot: bytes): # FIXME: not being called anywhere?
        for action in actions:
            action_key = action.html
            if action_key not in self.unique_actions or not self.has_similar_action(action):
                self.unique_actions[action_key] = ActionInfo(action, before_html, after_html, before_screenshot,
                                                             after_screenshot)

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

    def add_page(self, state: PageState, eq_class) -> EquivalenceClass:
        self.added_urls.add(normalize_url(state.url))
        if eq_class is None:
            # print(f"Creating new equivalence class")
            eq_class = EquivalenceClass()
            self.classes.append(eq_class)
        else:
            # print("Adding page to existing equivalence class")
            pass
        eq_class.add_page(state)
        return eq_class




# this is the aggressive normalization
def normalize_url(url: str) -> str:
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    return urlunparse((scheme, netloc, path, '', '', ''))  # Ignoring the query and fragment

def get_chunks_llm(page_tree: str):
    message = anthropic_client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1000,
        temperature=0,
        system="You are a website annotator.\nYou have a Python function annotate_general_functionality(description: str, indices: (int, int)), you are to call annotate_general_functionality for each general functionality.\nYou are going to be given an accessibility tree of a web page, where every action has the word 'ACTION' in its line. \nEvery line is indexed with a number in [].\nYour task is to identify chunks of the web page responsible for general tasks on the web page. Each general functionality is a chunk. Each chunk is a general functionality. A general functionality should encapsulate all instances of a type of action.\nYou should only care about general tasks that a user may want to do specifically on this web page. You must ignore navigation, ads or recommendations. Given these requirements, you must try to include all lines of the tree in some general functionality.\nEvery chunk should include actions, and chunks shouldn't have any overlap. \nFor every general functionality, give me the start and end indices of that chunk. Make your general functionality very inclusive and general. The indices are inclusive. If you are unsure about where to start the chunk, give the larger index. If you are unsure about where to end the chunk, give the smaller index.\nGeneral functionality may be a section of the website which performs the same type of action but on different instances of the same object type, group these into the same general functionality.\nIf a general functionality is within the chunk of another general functionality, I want to combine these into one general functionality. \n\nFirst reason step-by-step, then give me you answer in the form:\n- annotate_general_functionality('some general functionality which does something', (1, 30))\n- annotate_general_functionality('some other general functionality which does some other thing', (59, 62))",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Accessibility Tree:\n{page_tree}"
                    }
                ]
            }
        ]
    )
    final_response = message.content[0].text

    pattern = r"annotate_general_functionality\('(.+)',\s*\((\d+),\s*(\d+)\)\)"

    matches = re.findall(pattern, final_response)
    results = list()
    for match in matches:
        string = match[0]
        start = int(match[1])
        end = int(match[2])
        if start and end and string:
            results.append((string, start, end))

    return results

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

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        # Check if the action is a pure link in the header or footer

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
        elif role.strip() in input_roles:
            action = Action(Action.Type.INPUT, xpath, html)
            action.set_tree_line(f"{role}: {ax_node['name']}")
            return None

    return None

def normalize_statictext_html(html: str):
    result = None
    return result

def search_chunk(chunk: Chunk, ax_html: str):
    for chunk_html in chunk.ordered_candidates:
        if element_similarity(chunk_html, ax_html) > 0.9:
            return True
    return False

def enumerated_ax_tree(obs: AxObservation):
    cleaned_tree = ''
    count = 0
    enumed_nodes = list()
    for i in range(len(obs.nodes_info)):
        node = obs.nodes_info[i]
        node_action = ax_node_to_action(node)

        if (node_action or node['properties'] or node['role'] not in ['img']):
            enumed_nodes.append(node)
            if node_action and node['name'].strip() != "":
                cleaned_tree += f"[{count}]{node['indent']}ACTION of {node['role']}: {node['name']}\n"
            else:
                if node['role'] == 'StaticText':
                    print('here\'s some text')
                    input(node['parent_html'])
                cleaned_tree += f"[{count}]{node['indent']}{node['role']}: {node['name']}\n"
            count += 1

    return cleaned_tree, enumed_nodes

def match_chunks(page_state: PageState, all_chunks: list[Chunk]):  # Should mutate page_state to give it chunk info
    page_axtree = page_state.obs
    count = 0
    for chunk in all_chunks:
        start_id = None
        end_id = None
        for i in range(len(page_axtree.nodes_info)):
            node = page_axtree.nodes_info[i]
            node_action = ax_node_to_action(node)

            if (node_action or node['properties'] or node['role'] not in ['img']):
                if search_chunk(chunk, node['html']):
                    if start_id is None:
                        start_id = count
                else:
                    if start_id is not None and end_id is None:
                        end_id = count
                count += 1
    return None

def get_chunks(page_state: PageState):
    enum_ax_tree, enumed_nodes = enumerated_ax_tree(page_state.obs)
    chunks = get_chunks_llm(enum_ax_tree)
    result = dict()

    for (string, start, end) in chunks:
        result[string] = copy.deepcopy(enumed_nodes[start:end+1])  # TODO, don't use a dictionary that's dumb af

    return result

def get_chunks_for_equiv_class(equiv_class: EquivalenceClass):
    pass