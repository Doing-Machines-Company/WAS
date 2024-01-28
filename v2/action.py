from enum import IntEnum
from typing import Optional

class Action:
    class Type(IntEnum):
        STOP = 0
        CLICK = 1
        INPUT = 2

    def __init__(self, action_type: 'Action.Type', html: str, input_string: Optional[str] = None):
        self.action_type = action_type
        self.html = html
        # self.xpath = xpath
        self.input_string = input_string if action_type == Action.Type.INPUT else None

    def set_input_string(self, input_string: str):
        self.input_string = input_string

    def __repr__(self) -> str:
        return str(f"{self.action_type.name}, {self.html}, {self.input_string if self.input_string else 'N/A'}")
