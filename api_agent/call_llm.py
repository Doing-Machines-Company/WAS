# call_llm.py

import re
import json5
import json
import logging
import asyncio
from typing import List, Union
from api_llm_handling import LLMMessage, AgentCall
from provider_helpers import (
    cerebras_call,
    anthropic_call,
    openai_call,
    together_call,
    google_call  # groq_call removed
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Define fallback model if needed
FALLBACK_MODEL = "gpt-4o-mini"

async def call_llm(
    messages: List[LLMMessage],
    provider: str = "cerebras",
    model: str = "llama-3.3-70b",
    max_tokens: int = 5000
) -> AgentCall:
    """
    Calls the specified LLM provider asynchronously with the given messages.
    Implements fallback logic in case of provider failure.
    """
    try:
        if provider == "cerebras":
            raw_response = await cerebras_call(messages, model, max_tokens)
        elif provider == "anthropic":
            raw_response = await anthropic_call(messages, model, max_tokens)
        elif provider == "openai":
            raw_response = await openai_call(messages, model, max_tokens)
        elif provider == "together":
            raw_response = await together_call(messages, model, max_tokens)
        elif provider == "google":
            raw_response = await google_call(messages, model, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        parsed_output = extract_json(raw_response)
        return AgentCall(
            messages=messages,
            llm_response=raw_response,
            parsed_output=parsed_output
        )

    except Exception as e:
        logger.error(f"Error with provider '{provider}': {e}")
        # Fallback logic: try OpenAI if not already using it.
        if provider != "openai":
            logger.info(f"Falling back to OpenAI with model '{FALLBACK_MODEL}'")
            try:
                raw_response = await openai_call(messages, FALLBACK_MODEL, max_tokens)
                parsed_output = extract_json(raw_response)
                return AgentCall(
                    messages=messages,
                    llm_response=raw_response,
                    parsed_output=parsed_output
                )
            except Exception as fallback_e:
                logger.error(f"Fallback to OpenAI failed: {fallback_e}")

        return AgentCall(
            messages=messages,
            llm_response="",
            parsed_output=None
        )


def extract_json(raw_response: str) -> List[Union[dict, list, str]]:
    """
    Extracts JSON blocks from the raw response.
    """
    json_blocks = re.findall(
        r"```json\s*(\{.*?\}|\[.*?\])\s*```",
        raw_response,
        re.DOTALL | re.IGNORECASE
    )
    results = []
    for idx, block in enumerate(json_blocks, start=1):
        try:
            results.append(json5.loads(block.strip()))
        except json5.JSONDecodeError:
            try:
                results.append(json.loads(block.strip()))
            except json.JSONDecodeError:
                results.append(block.strip())
    return results
