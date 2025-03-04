# provider_helpers.py

import json
import json5
import re
from typing import List
from api_llm_handling import LLMMessage
from initialize_clients import (
    anthropic_client,
    cerebras_client,
    together_client,
    openai_client,
    google_client
)


# Async Cerebras call
async def cerebras_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    formatted_messages = [{"role": msg.message_role, "content": msg.content} for msg in messages]
    completion = await cerebras_client.chat.completions.create(
        messages=formatted_messages,
        model=model,
        stream=False,
        max_tokens=max_tokens,
        temperature=0,
        top_p=1
    )
    return completion.choices[0].message.content


# Async Anthropic call
async def anthropic_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    system_segments = [msg.content for msg in messages if msg.message_role == "system"]
    system_text = "\n".join(system_segments)
    user_segments = [{"role": "user", "content": msg.content} for msg in messages if msg.message_role == "user"]

    message = await anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system_text,
        messages=user_segments
    )
    return message.content[0].text


# Async OpenAI call
async def openai_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    openai_msgs = [{"role": msg.message_role, "content": msg.content} for msg in messages]
    completion = await openai_client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=max_tokens,
        messages=openai_msgs
    )
    return completion.choices[0].message.content


# Async Together call
async def together_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    together_msgs = [{"role": msg.message_role, "content": msg.content} for msg in messages if
                     msg.message_role == "user"]
    response = await together_client.chat.completions.create(
        model=model,
        messages=together_msgs,
        max_tokens=max_tokens,
        temperature=0,
        top_p=1,
        top_k=50,
        repetition_penalty=1,
        stop=["<|eot_id|>"],
        stream=False,
    )
    return response.choices[0].message.content


# Async Google call
async def google_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    system_text = "\n".join([msg.content for msg in messages if msg.message_role == "system"])
    user_text = "\n".join([msg.content for msg in messages if msg.message_role == "user"])
    # Combine system and user texts as needed
    full_text = user_text.strip() if not system_text else f"{system_text.strip()}\n{user_text.strip()}"

    generation_config = {
        "temperature": 0,
        "top_p": 1,
        "top_k": 40,
        "max_output_tokens": max_tokens,
        "response_mime_type": "text/plain",
    }

    # Using the async call via the genai client
    response = await google_client.aio.models.generate_content(
        model=model,
        contents=full_text,
        generation_config=generation_config
    )
    return response.text


# Helper function for extracting JSON blocks remains unchanged
def extract_json(raw_response: str) -> List:
    json_blocks = re.findall(
        r"```json\s*(\{.*?\}|\[.*?\])\s*```",
        raw_response,
        re.DOTALL | re.IGNORECASE
    )
    results = []
    for idx, block in enumerate(json_blocks, start=1):
        try:
            results.append(json5.loads(block.strip()))
        except json5.JSONDecodeError as e:
            try:
                results.append(json.loads(block.strip()))
            except json.JSONDecodeError:
                results.append(block.strip())
    return results
