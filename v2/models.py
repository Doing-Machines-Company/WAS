from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional, Union

# Terminology:
#   - 
# Note: A trajectory is an alternating list of PageObservation and Action
#       This is never explicitly stored in our implementation, it is passed incrementally through to register_action

class PageObservation(ABC):

    # observations can be compared
    @abstractmethod
    def __eq__(self, other : PageObservation) -> bool:
        pass

class ActionBase(ABC):

    @abstractmethod
    def __str__(self):
        pass

# begin action definitions

class Stop(ActionBase):

    def __str__(self) -> str:
        return "Stop"

class Click(ActionBase):

    elem_xpath: str

    def __str__(self) -> str:
        return f"Click[{self.elem_xpath}]"

# all actions
# Action = Stop | Click[xpath_str] | Input[xpath_str, input_str] | GOTO[url_str]
Action = Union[Stop, Click]

Model = str

class Agent(ABC):
    model : Model

    @abstractmethod
    def __init__(intent: str, starting_observation : PageObservation):
        pass

    # take note of a transition (in the "observation graph"). A sequence of these calls forms a trajectory
    @abstractmethod
    def register_action(action : Action, new_observation : PageObservation):
        pass

    # maybe prompt the model, a response from the model
    @abstractmethod
    def get_next_action(self) -> Action: # Needs some sense of current task
        pass

    # forget your memory (if you have any)
    @abstractmethod
    def reset():
        pass

class WebDriver(ABC):

    agent: Agent
    knowledge_base: Any

    def __init__(self, agent, knowledge_base: Any):
        self.agent = agent
        self.knowledge_base = knowledge_base
    # @abstractmethod
    # def init(self, intent: str, starting_url: str):
    #     pass

    @abstractmethod
    def observe_state() -> PageObservation:
        pass

    # user may want to store state here, ie. summarizing memory to be passed in next observation
    @abstractmethod
    def apply(a : Action):
        pass

    def process_intent(self, intent: str, starting_url: str):

        self.init(intent=intent, starting_url=starting_url)
        cur_obs : PageObservation = self.observe_state()
        self.agent.init(intent, cur_obs)

        action = None
        while action != Stop:
            
            agent_response : str = self.agent.prompt()
            action : Action = self.agent.parse_action(agent_response)

            self.apply(action)

            cur_obs = self.observe_state()
            self.agent.register_action(action, cur_obs)