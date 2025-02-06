# call_llm.py

import re
import json5
import json
import logging
import asyncio
from typing import List, Optional, Union, Any
from api_llm_handling import LLMMessage, AgentCall
from provider_helpers import (  # has dependence in initialize_clients
    cerebras_call,
    anthropic_call,
    openai_call,
    together_call,
    groq_call,
    google_call
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Define fallback model if needed
FALLBACK_MODEL = "claude-3-5-sonnet-latest"

async def call_llm(
    messages: List[LLMMessage],
    provider: str = "cerebras",
    model: str = "llama-3.3-70b",
    max_tokens: int = 5000
) -> AgentCall:
    """
    Calls the specified LLM provider with the given messages.
    Returns an AgentCall containing the raw LLM response and a list of parsed JSON payloads or raw JSON strings.
    Implements fallback logic in case of provider failure.
    """
    try:
        if provider == "cerebras":
            raw_response = await asyncio.to_thread(cerebras_call, messages, model, max_tokens)
        elif provider == "anthropic":
            raw_response = await asyncio.to_thread(anthropic_call, messages, model, max_tokens)
        elif provider == "openai":
            raw_response = await asyncio.to_thread(openai_call, messages, model, max_tokens)
        elif provider == "together":
            raw_response = await asyncio.to_thread(together_call, messages, model, max_tokens)
        elif provider == "groq":
            raw_response = await asyncio.to_thread(groq_call, messages, model, max_tokens)
        elif provider == "google":
            raw_response = await asyncio.to_thread(google_call, messages, model, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        # Extract JSON blocks from the response
        parsed_output = extract_json(raw_response)

        return AgentCall(
            messages=messages,
            llm_response=raw_response,
            parsed_output=parsed_output
        )

    except Exception as e:
        logger.error(f"Error with provider '{provider}': {e}")
        # Implement fallback logic if desired
        if provider != "anthropic":
            logger.info(f"Falling back to Anthropic with model '{FALLBACK_MODEL}'")
            try:
                raw_response = await asyncio.to_thread(anthropic_call, messages, FALLBACK_MODEL, max_tokens)
                parsed_output = extract_json(raw_response)
                return AgentCall(
                    messages=messages,
                    llm_response=raw_response,
                    parsed_output=parsed_output
                )
            except Exception as fallback_e:
                logger.error(f"Fallback to Anthropic failed: {fallback_e}")

        # If fallback also fails or provider is already Anthropic
        return AgentCall(
            messages=messages,
            llm_response="",
            parsed_output=None
        )


def extract_json(raw_response: str) -> List[Union[dict, list, str]]:
    """
    Extracts all JSON blocks from the raw LLM response.
    For each JSON block:
        - Try parsing with json5.
        - If it fails, try parsing with the standard json module.
        - If both fail, return the raw JSON string.
    Returns a list of parsed JSON objects and raw JSON strings.
    """
    # Regex to find all ```json ... ``` blocks
    json_blocks = re.findall(r"```json\s*(\{.*?\}|\[.*?\])\s*```", raw_response, re.DOTALL | re.IGNORECASE)

    results = []
    for idx, block in enumerate(json_blocks, start=1):
        parsed = None
        try:
            # Attempt to parse the JSON5 block
            parsed = json5.loads(block.strip())
            results.append(parsed)
        except json5.JSONDecodeError as e:
            logger.error(f"JSON5 parsing error in block {idx}: {e}")
            try:
                # Attempt to parse with standard json
                parsed = json.loads(block.strip())
                results.append(parsed)
            except json.JSONDecodeError as e_json:
                logger.error(f"Standard JSON parsing error in block {idx}: {e_json}")
                # Append the raw JSON string if both parsers fail
                results.append(block.strip())

    return results