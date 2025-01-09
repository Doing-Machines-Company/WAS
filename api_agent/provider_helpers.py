# provider_helpers.py

import re
import json
from typing import List
from api_llm_handling import LLMMessage
from initialize_clients import (
    anthropic_client,
    cerebras_client,
    together_client,
    groq_client,
    openai_client,
    google_client
)


def cerebras_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    formatted_messages = [{"role": msg.message_role, "content": msg.content} for msg in messages]
    completion = cerebras_client.chat.completions.create(
        messages=formatted_messages,
        model=model,
        stream=False,
        max_tokens=max_tokens,
        temperature=0,
        top_p=1
    )
    return completion.choices[0].message.content


def anthropic_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    system_segments = [msg.content for msg in messages if msg.message_role == "system"]
    user_segments = [msg.content for msg in messages if msg.message_role == "user"]

    message = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        system=system_segments,
        messages=user_segments
    )
    return message.content[0].text


def openai_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    openai_msgs = [{"role": msg.message_role, "content": msg.content} for msg in messages]
    completion = openai_client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=max_tokens,
        messages=openai_msgs
    )
    return completion.choices[0].message.content


def together_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    together_msgs = [{"role": msg.message_role, "content": msg.content} for msg in messages if
                     msg.message_role == "user"]
    response = together_client.chat.completions.create(
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


def groq_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    groq_msgs = [{"role": msg.message_role, "content": msg.content} for msg in messages]
    completion = groq_client.chat.completions.create(
        model=model,
        messages=groq_msgs,
        temperature=0,
        max_tokens=max_tokens,
        top_p=1,
        stream=False,
        stop=None,
    )
    return completion.choices[0].message.content


def google_call(messages: List[LLMMessage], model: str, max_tokens: int) -> str:
    system_text = "\n".join([msg.content for msg in messages if msg.message_role == "system"])
    user_text = "\n".join([msg.content for msg in messages if msg.message_role == "user"])

    generation_config = {
        "temperature": 0,
        "top_p": 1,
        "top_k": 40,
        "max_output_tokens": max_tokens,
        "response_mime_type": "text/plain",
    }

    model_instance = google_client.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
        system_instruction=system_text.strip()
    )

    chat_session = model_instance.start_chat(history=[])
    return chat_session.send_message(user_text.strip()).text
