from enum import IntEnum
from typing import Optional, List

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

    def __init__(self, action_type: 'Action.Type', xpath: str, html: str, tree_line: str = "", input_string: Optional[str] = None, trajectory: List['Action'] = [], friendly_xpath : Optional[str]= None):
        self.action_type = action_type
        self.html = html
        self.xpath = xpath
        self.input_string = None # input_string if action_type == Action.Type.INPUT else None
        self.tree_line = tree_line
        self.trajectory = trajectory #added trajectory to show how the action can be 'created', an empty traj indicates existence at base state of url 
        self.friendly_xpath = friendly_xpath
    def set_input_string(self, input_string: str):
        self.input_string = input_string

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
        return str(f"{self.action_type.name}{'(' + self.input_string + ')' if self.input_string else ''}:{self.xpath}({self.html[:100]})")