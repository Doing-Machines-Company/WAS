from openai import OpenAI
import os
import re
import json

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

def call_llm(prompt, model_name='gpt-3.5-turbo-1106'):
    if model_name.startswith('gpt'):
        response = client.chat.completions.create(
            model=model_name,
            # model="gpt-3.5-turbo-1106",
            messages=prompt,
            temperature=0,
            max_tokens=1500,
            # top_p=0,
            seed=12345678
        )

        result = response.choices[0].message.content
        print(f"GPT RAW RETURN CALL: {result}")

        pattern1 = r"'''(\d+):([^']*)'''"
        pattern2 = r"```(\d+):([^']*)```"


        match1 = re.search(pattern1, result, re.DOTALL)
        match2 = re.search(pattern2, result, re.DOTALL)

        if match1:
            final_index = match1.group(1).strip()
            final_string = match1.group(2).strip()
            return (final_index, final_string)
        elif match2:
            final_index = match2.group(1).strip()
            final_string = match2.group(2).strip()
            return (final_index, final_string)
        else:
            Exception("CALL RETURN FORMATTING FAIL")


def llm_manage_memory(prompt, model_name='gpt-3.5-turbo-1106'):
    if model_name.startswith('gpt'):
        response = client.chat.completions.create(
            model=model_name,
            # model="gpt-3.5-turbo-1106",
            messages=prompt,
            temperature=0,
            max_tokens=1500,
            # top_p=0,
            seed=12345678
        )

        result = response.choices[0].message.content
        print(f"GPT RAW RETURN MEMORY: {result}")

        pattern1 = r"'''(.*?)\|(.*?)'''"
        pattern2 = r"```(.*?)\|(.*?)```"


        match1 = re.search(pattern1, result)
        match2 = re.search(pattern2, result)
        if match1:
            string_left = match1.group(1).strip()
            string_right = match1.group(2).strip()
            result = (string_left, string_right)
            print("RESULT 1")
            print(result)
            return result
        elif match2:
            string_left = match2.group(1).strip()
            string_right = match2.group(2).strip()
            result = (string_left, string_right)
            print("RESULT 2")
            print(result)
            return result
        else:
            print("FUCK!!!!")
            Exception("CALL RETURN FORMATTING FAIL")