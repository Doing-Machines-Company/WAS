from __future__ import annotations
from models import *
from typing import Any, Optional, Union

class SimpleObservation(PageObservation):

    acc_tree : str
    page_html : str
    url : str

    def __eq__(self, other : SimpleObservation):
        return self.acc_tree == other.acc_tree
    
class VisitedSetAware(Agent):

    HTML = str

    clicked_xpaths: set[str]
    past_url_actions: dict[HTML, Union[str, None]]

    def __init__(self):
        pass

    def register_action(self, action: Action, new_observation: SimpleObservation):
        new_page_html = new_observation.page_html

        if isinstance(action, Click):
            # business logic to "squash" new transition / action into your state
            self.clicked_xpaths.add()

class PromptingSummarizing(Agent):

    @abstractmethod
    def prompt() -> str:
        pass

    @abstractmethod
    def parse_response() -> Action:
        pass

    def get_next_action(self) -> Action:
        res = self.prompt()
        return self.parse_response(res)
