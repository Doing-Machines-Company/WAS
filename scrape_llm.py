from openai import OpenAI
import os
import re
import json


openai_api_key = os.getenv('OPENAI_API_KEY')

openai_client = OpenAI(api_key=openai_api_key)

def use_gpt_fill_input(memory, website_info, outerHTML):
    messages = [
        {"role": "system",
         "content": "You are an AI assistant that generates example input strings for HTML elements. Use information from the memory I will give you when needed. You have a python function give_example() which takes a string, you must use to return your final answer. "},
        {"role": "user",
         "content": f"Given the memory: {memory}, website screenshot: {website_info}, and outerHTML: {outerHTML}, reason step by step then give me the text that can be used to fill the input box using the python function give_example()."}
    ]

    # Call GPT-4o with the messages
    response = openai_client.chat.completions.create(
        model='gpt-4o',
        messages=messages,
        max_tokens=100,
        temperature=0
    )


    result = response.choices[0].message.content.strip()
    pattern = r'give_example\(["\']([^"\']*)["\']\)'


    match = re.search(pattern, result)

    if match:
        parameter = match.group(1)
        return parameter
    else:
        return ""

