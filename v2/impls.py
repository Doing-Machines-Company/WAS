from __future__ import annotations
from models import *
from typing import Any, Optional, Union
from prompt_constructors import *
from call_llm import *

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

class Action:
    pass
class InteractionAgent(Agent):
    def __init__(self, intent : str, starting_observation : PageObservation):
        self.intent = intent

    def register_action(action : Action, new_observation : PageObservation):
        # Should really do nothing for this agent
        pass


    def get_next_action(self, cur_obs : PageObservation) -> Action:
        # TODO Get URL from scrape
        pass


class MemorizingAgent(Agent):
    def __init__(self, intent: str, starting_observation: PageObservation):
        self.intent = intent
        self.old_observation = None
        self.newer_observation = starting_observation

    def register_action(action: Action, new_observation: PageObservation):
        # TODO GET RELEVANT KNOWLEDGE FROM ACTION and OBSERVATION DIFFERENCES
        pass

    def get_next_action(self, cur_obs: PageObservation) -> Action:
        self.old_observation = self.newer_observation
        self.newer_observation = cur_obs
        pass


class URLAgent(Agent):
    def __init__(self, intent : str, starting_observation : PageObservation):
        self.intent = intent

    def register_action(action : Action, new_observation : PageObservation):
        # Should really do nothing for this agent
        pass

    def get_next_action(self, cur_obs: PageObservation) -> Action:
        # TODO Get URL from scrape, NEEDS TO KNOW WHAT HAS BEEN DONE
        # TODO NEEDS TO GRAB FROM WEB DRIVER OR ENVIRONMENT
        pass

class BaseAgent(Agent):

    def __init__(self, intent : str, starting_observation : PageObservation):
        self.intent = intent
        self.last_action = None
        self.old_obs = None
        self.new_obs = starting_observation
        self.phase = 'choosing_elements' # or 'choosing_elements' (or 'handling_memory')
    def register_action(action : Action, new_observation : PageObservation):
        pass

    def construct_prompt(self, last_action : Action, old_obs : PageObservation, new_obs : PageObservation) -> str:
        if self.phase == 'choosing_url':
            return construct_url_prompt(new_obs)
        elif self.phase == 'choosing_elements':
            return construct_elements_prompt(new_obs)
        elif self.phase == 'handling_memory':
            return construct_memory_prompt(last_action, old_obs, new_obs)
        else:
            raise Exception('Invalid phase prompt construct')


    def get_next_action(self, cur_obs : PageObservation) -> Action:
        prompt_for_agent, answer_values = self.construct_prompt(cur_obs, model_name = 'gpt-3.5-turbo-1106') # prompt_for_agent : str, answer_values : list[Actions]
        answer_index = call_llm(prompt_for_agent, model_name = 'gpt-3.5-turbo-1106')
        return answer_values[answer_index]