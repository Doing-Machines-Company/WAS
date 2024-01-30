from __future__ import annotations
from models import *
from typing import Any, Optional, Union
from prompt_constructors import * # THESE ARE WEBSHOP SPECIFIC
from call_llm import *
from typing import Optional
from action import Action
from enum import Enum, auto
from typing import Optional



class Phase(Enum):
    CHOOSING_URL = auto()
    CHOOSING_ELEMENTS = auto()
    # HANDLING_MEMORY = auto()

class BaseAgent(Agent):

    def __init__(self, intent: str, starting_observation: PageObservation = None):
        self.intent = intent
        self.last_action = None
        self.old_obs = None
        self.new_obs = starting_observation
        self.phase = Phase.CHOOSING_ELEMENTS # or 'choosing_elements' (or 'handling_memory') # TODO MAKE ENUM TYPE

        self.archive = []
        self.task_memory = []  #
        self.info_memory = []  # should really only need to remember information that needs to be synthesised
        self.environmental_changes = dict()
    def register_action(action: Action, new_observation: PageObservation):
        pass

    def reset():
        pass

    def construct_prompt(self, last_action: Action, old_obs: PageObservation, new_obs: PageObservation, model_name) -> str:
        match self.phase:
            case Phase.CHOOSING_URL:
                return construct_url_prompt(self.intent, new_obs, model_name)
            case Phase.CHOOSING_ELEMENTS:
                return construct_elements_prompt(self.intent, new_obs, model_name)
            # case Phase.HANDLING_MEMORY:
                # return construct_memory_prompt(self.intent, last_action, old_obs, new_obs, model_name)
            case _:
                raise Exception(f'Invalid phase prompt construct, HOW????? {self.phase}')


    def get_next_action(self, cur_obs: PageObservation) -> Action:
        self.old_obs = self.new_obs
        self.new_obs = cur_obs # TODO PROCESS THESE cur_obs to reflect environmental changes cause by the agents action history
        prompt_for_agent, answer_values = self.construct_prompt(self.last_action, self.old_obs, self.new_obs, model_name = 'gpt-4-0125-preview') # prompt_for_agent: str, answer_values: list[Actions]
        (final_index, final_stirng) = call_llm(prompt_for_agent, model_name = 'gpt-4-0125-preview')
        if final_index:
            desired_action = answer_values[int(final_index)]
            if desired_action.action_type == Action.Type.INPUT:
                desired_action.set_input_string(final_stirng)
            return desired_action
        return Action(Action.Type.STOP, None, None)
