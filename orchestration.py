from models import *

"""
--------------------------------------------------------------------------------
The executive controller (EC) is responsible for taking in an observation of a website 
formatted into chunks, and selecting which chunk to investigate further, where a chunk
is a grouping of related actions and text (i.e. orders, side panel for purchasing, adding
 to cart, etc., search results, navbar). It is also responsible for setting a plan
 and choosing whether to dispatch other modules (memory handler). Concretely, we have:

 INPUTS: PROCESSED PAGE OBSERVATION, OBJECTIVE
 OUTPUT: PLAN, CHUNK TO INVESTIGATE, DISPATCH MEMORY HANDLER (BOOLEAN)
--------------------------------------------------------------------------------
The action decider (AD) is responsible for taking in an observation of a chunk
of a website and selecting which action to perform. 

INPUTS: CHUNK, OBJECTIVE, PLAN
OUTPUT: ACTION
--------------------------------------------------------------------------------
The memory module (MM) is responsible for parsing through a website 

"""


class ExecutiveController(Agent):
    model : Model
    system_prompt : str
    @abstractmethod
    def __init__(intent: str):
        pass
   
   #will see a processed version of the webpage, including chunks
    @abstractmethod
    def infer(obs : PageObservation) -> Action: # Needs some sense of current task
        pass

class ActionDecider(Agent):
    model : Model
    system_prompt : str
    @abstractmethod
    def __init__(intent: str):
        pass
   
   #will see a single chunk
    @abstractmethod
    def infer(obs : PageObservation) -> Action: # Needs some sense of current task
        pass

class MemoryModule(Agent):
    model : Model
    system_prompt : str
    @abstractmethod
    def __init__(intent: str):
        pass
    def infer(obs : PageObservation) -> Action: # Needs some sense of current task
        pass