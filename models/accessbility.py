from __future__ import annotations
import os 
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(
                  os.path.dirname(__file__), 
                  os.pardir)
)
sys.path.append(PROJECT_ROOT)
from models.states import InferencePageState
from models.actions import *
import re 
from abc import ABC, abstractmethod
class PageObservation(ABC):

    # observations can be compared
    @abstractmethod
    def __eq__(self, other : PageObservation) -> bool:
        pass
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
                        "nodeId": obs_node_id,  #LATER CHANGED AFTER DFS
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
        # node_id_counter = 0
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
            # node["nodeId"] = node_id_counter  # RESETS NODE IDs TO BE ENUMERATED
            # node_id_counter += 1
            cleaned_nodes.append(node)
        self.nodes_info = cleaned_nodes

    def __eq__(self):
        pass

    def __str__(self):
        tree_str = ''
        for node in self.nodes_info:
            tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str

class InferenceAxtree:

    #  we get axnodes which we roll into a pagestate, which we will roll into an InferencePageState, which we will then reroll into a InferenceAxtree
    #  TODO give header and footer actions
    def __init__(self, scrape_info: InferencePageState, special_actions = None, use_scrape = True):
        self.scrap_info = scrape_info
        self.action_effect_lib = dict()
        self.action_lib = dict()
        self.action_number_lib = dict()
        self.use_scrape = use_scrape
        self.live_actions = []
        self.live_action_effects = []

        count = 0
        self.tree_str = ''
        self.debug_tree = ''

        for indefinite_action in special_actions:
            self.tree_str += f"[{count}] {str(indefinite_action)}\n"
            self.debug_tree += f"[{count}] {str(indefinite_action)} (SPECIAL ACTION) \n"
            self.live_actions.append(indefinite_action)
            self.live_action_effects.append("SPECIAL ACTION")
            count += 1

        for attempted_match in scrape_info.matched_actions:
            curr_action = attempted_match.curr_action
            scraped_action = attempted_match.matched_scrape_action
            if scraped_action:
                action_effect = scraped_action.action_effect
                if action_effect is None:
                    # TODO: does this ever happen???
                    # action_effect = curr_action.action.tree_line
                    action_effect = ''  # matched in found url state but it somehow doesn't have an action effect
                numbering = scraped_action.number
            else:
                numbering = '-1'
                # action_effect = curr_action.action.tree_line
                action_effect = ''  # not matched in found url state we don't give an action effect
            self.action_effect_lib[curr_action.ax_node_index] = action_effect
            self.action_number_lib[curr_action.ax_node_index] = numbering
            self.action_lib[curr_action.ax_node_index] = curr_action




        if not self.use_scrape:
            for node in self.scrap_info.ax_nodes:
                if node['nodeId'] in self.action_effect_lib:
                    self.tree_str += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.debug_tree += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    count += 1
                    self.live_actions.append(self.action_lib[node['nodeId']])
                    self.live_action_effects.append(self.action_effect_lib[node['nodeId']])
                else:
                    self.tree_str += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.debug_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
        else:
            for node in self.scrap_info.ax_nodes:
                if node['nodeId'] in self.action_effect_lib:
                    self.tree_str += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + "\n"
                    self.debug_tree += f"[{count}] {node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + " {" + self.action_effect_lib[node['nodeId']] + "}" + f" **MATCHED TO {self.action_number_lib[node['nodeId']]}**" + "\n"
                    count += 1
                    self.live_actions.append(self.action_lib[node['nodeId']])
                    self.live_action_effects.append(self.action_effect_lib[node['nodeId']])
                else:
                    self.debug_tree += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"
                    self.tree_str += f"{node['indent']}{node['role']} {repr(node['name'])} " + " ".join(
                        node["properties"]) + "\n"




    def get_action_from_index(self, index: int) -> IndefiniteAction:
        return self.live_actions[index]

    def get_debug_tree(self):
        return self.debug_tree

    def get_action_effect_from_index(self, index: int) -> str:
        return self.live_action_effects[index]


    def __str__(self):
        return self.tree_str