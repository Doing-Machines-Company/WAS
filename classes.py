import copy
from enum import IntEnum
# from drivers import AxObservation
from models import *
from typing import Optional, List, Any
from dataclasses import dataclass
from scrapecode.element_similarity import element_similarity
import re

PlaywrightPage = Any
CDPSession = Any
AxNode = Any  # TODO: make this a dataclass

class AxObservation(PageObservation):
    def __init__(self, axtree, url):
        self.axtree = axtree
        self.url = url
        node_id_to_idx = {}
        for idx, node in enumerate(self.axtree):
            node_id_to_idx[node["nodeId"]] = idx  # NOW WE HAVE A NEW ID SYSTEM, GOES UP EASIER FOR BOT

        self.nodes_info = []
        def dfs(idx: int, obs_node_id: str, depth: int) -> str:
            pua_cleaner = re.compile('[\ue000-\uf8ff]')
            node = self.axtree[idx]
            indent = "\t" * depth
            valid_node = True
            try:
                role = node["role"]["value"]
                name = node["name"]["value"]
                name = pua_cleaner.sub('', name)
                properties = []
                for property in node.get("properties", []):
                    try:
                        ignored_properties = {"focusable", "editable", "readonly", "level", "settable", "multiline", "invalid"}
                        if property["name"] in ignored_properties:
                            continue
                        properties.append(f'{property["name"]}: {property["value"]["value"]}')
                    except KeyError:
                        pass
                # check valid
                if not role and not name.strip():
                    valid_node = False

                # empty generic node
                if not name.strip():
                    # if not properties:
                    if role in ["generic", "img", "list", "strong", "paragraph", "banner", "navigation", "Section",
                                "LabelText", "Legend", "listitem", "LineBreak", "ListMarker", "gridcell", "link"]:  # TODO, double check logic, I did this arbitrarily ripping things out
                        valid_node = False
                    # elif role in ["listitem"]:
                    #     include_in_nodes_info = False

                if valid_node:
                    node_info = {
                        "nodeId": obs_node_id,
                        "name": name,
                        "role": role,
                        "indent": indent,
                        "properties": properties,
                        "html": node['html'],
                        "xpath": node['xpath'],
                        "parent_html": node['parent_html'] if 'parent_html' in node else None
                    }
                    self.nodes_info.append(node_info)



            except Exception as e:
                valid_node = False

            for _, child_node_id in enumerate(node["childIds"]):
                if child_node_id not in node_id_to_idx:
                    continue
                # mark this to save some tokens
                child_depth = depth + 1 if valid_node else depth
                dfs(node_id_to_idx[child_node_id], child_node_id, child_depth)

        dfs(0, self.axtree[0]["nodeId"], 0)
        """further clean accesibility tree"""
        cleaned_nodes = []
        node_id_counter = 0
        for node in self.nodes_info:
            # remove statictext if the content already appears in the previous line
            if node["role"] == "StaticText":
                prev_nodes = cleaned_nodes[-3:]
                found = False
                for prev in prev_nodes:
                    if node["name"] in prev["name"]:
                        found = True
                if found:
                    continue
            node["nodeId"] = node_id_counter
            node_id_counter += 1
            cleaned_nodes.append(node)
        self.nodes_info = cleaned_nodes

    def __eq__(self):
        pass

    def __str__(self):
        tree_str = ''
        for node in self.nodes_info:
            tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str


class Action:
    class Type(IntEnum):
        STOP = 0
        CLICK_IMPORTANT = 1
        INPUT = 2
        CLICK_LINK = 3
        GOTO_URL = 4
        CLICK_GENERAL = 5
        CLICK_RADIO = 6
        CLICK_CHECKBOX = 7
        GET_NEXT_SUBTASK_FINISHED = 8
        GET_NEXT_SUBTASK_IMPOSSIBLE = 9
        GO_BACK = 10
        SELECT_GENERAL = 11

    def __init__(self, action_type: 'Action.Type', xpath: str, html: str, tree_line: str = "", input_string: Optional[str] = None, trajectory: List['Action'] = [], friendly_xpath : Optional[str]= None):
        self.action_type = action_type
        self.html = html
        self.xpath = xpath
        self.input_string = None # input_string if action_type == Action.Type.INPUT else None
        self.tree_line = tree_line
        self.desired_option = None
        self.trajectory = trajectory #added trajectory to show how the action can be 'created', an empty traj indicates existence at base state of url
        self.friendly_xpath = friendly_xpath
        # self.action_effect = action_effect
    def set_input_string(self, input_string: str):
        self.input_string = input_string

    # def set_action_effect(self, action_effect: str):
    #     self.action_effect = action_effect

    def set_desired_option(self, desired_option: str):
        self.desired_option = desired_option

    def set_xpath(self, xpath: str):
        self.xpath = xpath

    def set_tree_line(self, tree_line: str):
        self.tree_line = tree_line

    def set_trajectory(self, trajectory: List['Action']):
        self.trajectory = trajectory
    def set_friendly_xpath(self, friendly_xpath: str):
        self.friendly_xpath = friendly_xpath

    def display_trajectory(self):
        if not self.trajectory:
            return "EMPTY"
        trajectory = ""
        for traj in self.trajectory:
            trajectory += traj.tree_line + '\n'
        return trajectory

    def __repr__(self) -> str:
        return str(f"{self.action_type.name if self.action_type else ''}{'(' + self.input_string + ')' if self.input_string else ''}:{self.xpath}({self.html[:100]})")


#TODO:
#fix equivalence class representations
#thread compliance with action stack/queue
#combine locks into single context lock
#A* (LLM-guided) scrape?

@dataclass
class ScrapeAction:
    action: Action
    before_html: str
    after_html: str
    before_screenshot: bytes | str
    after_screenshot: bytes | str
    url: str
    action_effect: str | None


@dataclass
class IndefiniteAction:
    type_list: list[Action.Type]
    action: Action | None
    ax_node_index: int

@dataclass
class InferenceAction:
    curr_action: IndefiniteAction
    matched_scrape_action: ScrapeAction | None

@dataclass
class PageState:
    url: str
    ax_nodes: list[AxNode]
    html: str
    actions: list[IndefiniteAction]
    header_html: str
    footer_html: str



#removed some of the fields from pagestate, not sure if they will ultimately be needed?


#represents the union over all possible actions at an exact url
class URLState:
    def __init__(self, url):
        self.aliases : set[str] = {url} #all the urls that are associated with the same action set
        self.unique_samples: dict[str, list[ScrapeAction]] = {} #action set obtainable via any trajectories within this url

    def add_alias(self, url):
        self.aliases.add(url)

    #add sample if no duplicate and return True, otherwise return False
    def add_sample(self, sample: list[ScrapeAction]):
        representative_html = sample[0].action.html
        if representative_html not in self.unique_samples:
            self.unique_samples[representative_html] = sample
            return True
        return False
    #return (for now) percentage of actions from input page_state that can be matched by this urlstate
    def similarity_score(self, page_state : PageState) -> float:
        matched = 0.0
        total = len(page_state.actions)
        for indefinite_action in page_state.actions:
            action = indefinite_action.action
            if action.html in self.unique_samples: #attempt O(1) key lookup
                matched += 1
            elif any(element_similarity(action.html, sample_html) > .9 for sample_html in self.unique_samples.keys()):
                matched += 1
        if total != 0:
            print("Similarity score: ", matched / total)
            return matched / total
        else:
            print("NOTHING HERE TO SCRAPE")
            return 0

    #attempt to match a list of actions and return pairs of actions with matched actions
    def match_actions(self, action_list : list[IndefiniteAction]) -> list[InferenceAction]:
        '''

        @dataclass
        class InferenceAction:
            curr_action: Action
            type_list: list[Action.Type]
            matched_action: Action | None

        @dataclass
        class IndefiniteAction:
            type_list: list[Action.Type]
            action: Action | None

        :param action_list:
        :return:
        '''
        paired_actions = []
        for indefinite_action in action_list:
            action = indefinite_action.action  # aliasing in python is confusing
            max_score = 0
            matched_scrape_action = None
            if action.html in self.unique_samples:  # hash check using dictionary, should probably include all scraped htmls instead of representative
                matched_scrape_action = self.unique_samples[action.html][0]  # gets a ScrapeAction
                # resulting_action = InferenceAction(action, indefinite_action.type_list, matched_action, indefinite_action.ax_node_index)
            else:
                for sample_action_rep_html in self.unique_samples:
                    score = element_similarity(action.html, sample_action_rep_html)
                    if score == 1.0:
                        matched_scrape_action = self.unique_samples[sample_action_rep_html][0]  # ONLY A SINGLE ACTION MATCHED
                        #  NOTE ABOVE IS A SCRAPEACTION, NOT AN ACTION (WHICH IS CONTAINED IN SCRAPE ACTION)
                        break
                    elif score > max_score and score >= 0.9:
                        max_score = score
                        matched_scrape_action = self.unique_samples[sample_action_rep_html][0]

            # if matched_scrape_action:
            #     #  scraped action (action class that's in ScrapeAction class) should have a type
            #     indefinite_action.action.action_type = matched_scrape_action.action.action_type  # TODO IN THE CASE SOMEHOW THERE ISN'T A PERFECT ACTION LIST MATCH, THIS IS BAD, NEED PERFECT ACTION LIST MATCH IN ELEMENT SIMILARITY
            #     #  also, potentially more class aliasing issues

            resulting_action = InferenceAction(indefinite_action, matched_scrape_action)
            paired_actions.append(resulting_action)  # WILL APPEND NONE IF NO ACTION HAS SCORE >= 0.9
        return paired_actions

#represents a set of normalized urls
class URLStateManager:
    def __init__(self):
        self.urls : dict[str, URLState] = {}
    def add_url(self, url : str, state : URLState):
        if url not in self.urls:
            self.urls[url] = state
    def get_state(self, page_state : PageState) -> URLState:
        url = page_state.url
        if url in self.urls:
            return self.urls[url]
        else:
            max_score = 0
            matched_url_state = None
            for url_state in self.urls.values():
                score = url_state.similarity_score(page_state)
                if score > max_score:
                    max_score = score
                    matched_url_state = url_state
            if max_score >= .95:
                return matched_url_state
            else:
                return None

@dataclass
class InferencePageState:
    url: str
    ax_nodes: list[AxNode]
    html: str
    url_state: URLState
    matched_actions: list[InferenceAction]