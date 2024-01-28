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
        print(f"GPT RAW RETURN: {result}")

        pattern1 = r"\'\'\'(\d+)\'\'\'"
        pattern2 = r"\`\`\`(\d+)\`\`\`"

        match1 = re.search(pattern1, result, re.DOTALL)
        match2 = re.search(pattern2, result, re.DOTALL)

        if match1:
            final_answer = int(match1.group(1).strip())
            return final_answer
        elif match2:
            final_answer = int(match2.group(1).strip())
            return final_answer
        else:
            Exception("CALL RETURN FORMATTING FAIL")