# call_llm.py

import re
import json
import os
import anthropic
from cerebras.cloud.sdk import Cerebras
from typing import Optional
from api_llm_handling import LLMMessage, AgentCall


anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

cerebras_client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))


def call_llm(system_content: str, user_content: str,
             model: str = "llama-3.3-70b",
             max_tokens: int = 512) -> AgentCall:
    """
    Calls a Cerebras-based LLM with a system and user message.
    Returns an AgentCall containing the raw LLM response and
    any parsed JSON payload.
    """

    messages = [
        LLMMessage(message_role="system", content=system_content),
        LLMMessage(message_role="user", content=user_content)
    ]

    # Prepare for the cerebras call
    c_msgs = []
    for msg in messages:
        c_msgs.append({
            "role": msg.message_role,
            "content": msg.content
        })

    # ----- Perform the actual Cerebras call -----
    # This code snippet is per your example usage:
    raw_response = ""  # default in case of error
    try:
        completion = cerebras_client.chat.completions.create(
            messages=c_msgs,
            model=model,
            stream=False,
            max_tokens=max_tokens,
            temperature=0,
            top_p=1
        )
        raw_response = completion.choices[0].message.content
    except Exception as e:
        print("Error calling Cerebras:", e)
        # You might handle or log the error

    # ----- Extract JSON from the LLM response via regex -----
    parsed_output = None
    match = re.search(r"```json(.*?)```", raw_response, re.DOTALL)
    if match:
        try:
            json_str = match.group(1).strip()
            parsed_output = json.loads(json_str)
        except Exception as e:
            print("JSON parse error:", e)

    return AgentCall(messages=messages, llm_response=raw_response, parsed_output=parsed_output)
