from enum import IntEnum
from typing import Optional

class Action:
    class Type(IntEnum):
        STOP = 0
        CLICK_IMPORTANT = 1
        INPUT = 2
        CLICK_LINK = 3
        GOTO_URL = 4
        CLICK_SELECT = 5
        CLICK_GENERAL = 6
        CLICK_RADIO = 7
        CLICK_CHECKBOX = 8

    def __init__(self, action_type: 'Action.Type', xpath: str, html: str, tree_line: str = "", input_string: Optional[str] = None):
        self.action_type = action_type
        self.html = html
        self.xpath = xpath
        self.input_string = input_string if action_type == Action.Type.INPUT else None
        self.tree_line = tree_line

    def set_input_string(self, input_string: str):
        self.input_string = input_string

    def set_tree_line(self, tree_line: str):
        self.tree_line = tree_line

    def __repr__(self) -> str:
        return str(f"{self.action_type.name}, {self.xpath}, {self.html}, {self.input_string if self.input_string else 'N/A'}")