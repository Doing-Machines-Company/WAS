# api_llm_handling.py

from dataclasses import dataclass
from typing import List, Tuple, Optional, Any, Union

@dataclass
class LLMMessage:
    """
    Data class representing a single message input for an LLM call.
    message_role: "system" or "user"
    content: The text content for that role.
    """
    message_role: str
    content: str


@dataclass
class AgentCall:
    """
    Data class representing the result of an LLM call.
    - messages: The list of messages that formed the prompt for this call.
    - llm_response: Raw response from the LLM.
    - parsed_output: Any structured result we parse from llm_response (optional).
    """
    messages: List[LLMMessage]           # UPDATED: store the entire list of messages
    llm_response: Any
    parsed_output: Optional[List[Any]] = None