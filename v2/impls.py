from __future__ import annotations
from models import *
from typing import Any, Optional, Union
from prompt_constructors import * # THESE ARE WEBSHOP SPECIFIC
from call_llm import *
from enum import IntEnum
from typing import Optional



class Action:
    class Type(IntEnum):
        STOP = 0
        CLICK = 1
        INPUT = 2

    def __init__(self, action_type: 'Action.Type', html: str, xpath: str, input_string: Optional[str] = None):
        self.action_type = action_type
        self.html = html
        self.xpath = xpath
        self.input_string = input_string if action_type == Action.Type.INPUT else None

    def __repr__(self) -> (str, str, str, str):
        return (self.action_type.name, self.html, self.xpath, self.input_string if self.input_string else 'N/A')


class BaseAgent(Agent):

    def __init__(self, intent: str, starting_observation: PageObservation = None):
        self.intent = intent
        self.last_action = None
        self.old_obs = None
        self.new_obs = starting_observation
        self.phase = 'choosing_elements' # or 'choosing_elements' (or 'handling_memory') # TODO MAKE ENUM TYPE
    def register_action(action: Action, new_observation: PageObservation):
        pass

    def reset():
        pass

    def construct_prompt(self, last_action: Action, old_obs: PageObservation, new_obs: PageObservation, model_name) -> str:
        if self.phase == 'choosing_url':
            return construct_url_prompt(new_obs, model_name)
        elif self.phase == 'choosing_elements':
            return construct_elements_prompt(new_obs, model_name)
        elif self.phase == 'handling_memory':
            return construct_memory_prompt(last_action, old_obs, new_obs, model_name)
        else:
            raise Exception('Invalid phase prompt construct')


    def get_next_action(self, cur_obs: PageObservation) -> Action:
        self.old_obs = self.new_obs
        self.new_obs = cur_obs
        prompt_for_agent, answer_values = self.construct_prompt(self.last_action, self.old_obs, self.new_obs, model_name = 'gpt-3.5-turbo-1106') # prompt_for_agent: str, answer_values: list[Actions]
        answer_index = call_llm(prompt_for_agent, model_name = 'gpt-3.5-turbo-1106')
        # return answer_values[answer_index]
        return Action(Action.Type.CLICK, 'html', 'xpath', 'N/A')