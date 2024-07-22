from enum import IntEnum
from typing import Optional, List, Any, Union
from dataclasses import dataclass

import os 
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(
                  os.path.dirname(__file__), 
                  os.pardir)
)
sys.path.append(PROJECT_ROOT)

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
        self.special_effect = None # only should be used for special actions we add on like STOP

        # self.action_effect = action_effect
    def set_input_string(self, input_string: str):
        self.input_string = input_string

    # def set_action_effect(self, action_effect: str):
    #     self.action_effect = action_effect

    def set_desired_option(self, desired_option: str):
        self.desired_option = desired_option

    def set_special_effect(self, special_effect: str):
        self.special_effect = special_effect
    
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
        return str(f"{self.action_type.name if self.action_type else ''}{'(' + self.input_string + ')' if self.input_string else ''}:{self.xpath if self.xpath else ''}{'(' + self.html + ')' if self.html else ''}")

@dataclass
class ScrapeAction:
    action: Action
    before_html: str
    after_html: str
    before_screenshot: bytes | str
    after_screenshot: bytes | str
    url: str
    action_effect: str | None
    number: str 

@dataclass
class IndefiniteAction:
    type_list: list[Action.Type]
    action: Action | None
    ax_node_index: int

@dataclass
class InferenceAction:
    curr_action: IndefiniteAction
    matched_scrape_action: ScrapeAction | None