import anthropic
import re
import os
import string
from utils.inference_data import *
from groq import Groq
import json

# Set up the Anthropic API client
anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# Set up the Groq API client
groq_client = Groq()

def call_llm(prompt, provider="anthropic", model="claude-3-5-sonnet-20240620", max_tokens=1000):
    if provider == "anthropic":
        message = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        return message.content[0].text
    elif provider == "groq":
        completion = groq_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            stream=False,
            stop=None,
        )
        return completion.choices[0].message.content
    else:
        raise ValueError("Invalid provider. Choose 'anthropic' or 'groq'.")

def call_action_agent(task, task_details, ax_tree, world_memory, action_memory, context, provider="anthropic"):
    action_memory = str(action_memory)
    with open('prompts/new_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'ax_tree': ax_tree,
        'task': task,
        'task_details': task_details,
        'world_memory': world_memory,
        'action_memory': action_memory,
        'context': context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider)
    
    print(answer)
    input("Action call")

    pattern = r'choose\(\s*(\d+),\s*"([^"]*(?:\\.[^"]*)*)"\)'
    match = re.search(pattern, answer)

    if match:
        return (int(match.group(1)), match.group(2))

    return None

def call_memory_agent(web_agent_task, task_details, action_memory, world_memory, provider="anthropic"):
    action_memory = str(action_memory)
    with open('prompts/world_mem_prompt_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
        'task_details': task_details,
        'world_memory': world_memory,
        'action_memory': action_memory,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    input("World mem call")

    # pattern = r'"""([\s\S]*?)"""'
    # match = re.search(pattern, answer)

    # Step 1 & 2: Find the JSON object in the answer
    json_match = re.search(r'\{[\s\S]*}', answer)

    if json_match:
        json_str = json_match.group(0)

        try:
            # Step 3: Parse the JSON string
            parsed_json = json.loads(json_str)

            # Step 4: Extract the new_world_memory
            new_world_memory = parsed_json.get("new_world_memory")

            if new_world_memory is not None:
                return new_world_memory
            else:
                return "Error: 'new_world_memory' key not found in JSON"

        except json.JSONDecodeError:
            return "Error: Invalid JSON format"
    else:
        return "Error: No JSON object found in the answer"

def call_reflect_agent(action_number, reason_for_action, old_ax_tree, new_ax_tree, provider="anthropic"):
    with open('prompts/reflect_store_prompt_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'action_number': action_number,
        'reason_for_action': reason_for_action,
        'old_accessibility_tree': old_ax_tree,
        'new_accessibility_tree': new_ax_tree,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    input("Memory store call")

    json_match = re.search(r'\{.*\}', answer, re.DOTALL)
    if not json_match:
        print("Reflect Restore Error: No JSON object found in the LLM output")

    json_str = json_match.group(0)

    # Step 3: Parse the JSON string
    try:
        data = json.loads(json_str)
        old_web_page_purpose = data.get('old_web_page_purpose', '')
        action_effect = data.get('action_effect', '')
        return old_web_page_purpose, action_effect
    except json.JSONDecodeError:
        print("Reflect Restore Error: Invalid JSON in the LLM output")
        return None



def call_task_separator(web_agent_task, provider="anthropic"):
    with open('prompts/task_separator_prompt_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    
    answer = call_llm(prompt, provider='groq', model = 'llama-3.1-8b-instant')
    answer = answer.strip()

    # Step 1: Use regex to find the JSON object
    json_pattern = r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
    match = re.search(json_pattern, answer)

    if match:
        # Step 2: Extract the JSON string
        json_str = match.group(0)

        try:
            # Step 3: Parse the extracted JSON string
            parsed_json = json.loads(json_str)

            # Step 4: Extract the required information
            choices = parsed_json.get('choices', [])
            pairs = [(choice['text_area_number'], choice['desired_input']) for choice in choices]

            # Print the resulting list of tuples
            print(pairs)
        except json.JSONDecodeError:
            print("Task Separator: Failed to parse JSON. The extracted string might not be valid JSON.")
    else:
        print("Task Separator: No JSON object found in the answer.")

    return None

def call_task_clarifier(user_task, item_context_pairs, provider="anthropic"):
    with open('prompts/task_parser_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'user_task': user_task,
        'item_of_interest': item_context_pairs,
        'context': context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider)
    
    print(answer)
    input("Task clarifier call")

    pattern = r'"""([\s\S]*?)"""'
    match = re.search(pattern, answer)

    if match:
        return match.group(1).strip()

    return ""

def call_input_agent(user_task, agent_intent, task_details, input_ax_tree, context, hidden_inputs: list[HiddenInput], provider="anthropic"):
    with open('prompts/mass_input_prompt_json.txt', 'r') as f:
        prompt = f.read()

    formatted_hidden_items = ''
    for item in hidden_inputs:
        formatted_hidden_items += item.key.strip() + ': ' + item.description.strip() + '\n'

    formatted_hidden_items = formatted_hidden_items.strip()

    replacements = {
        'user_task': user_task,
        'agent_intent': agent_intent,
        'task_details': task_details,
        'input_ax_tree': input_ax_tree,
        'context': context,
        'hidden_items': formatted_hidden_items
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider)

    pattern = r'"text_area_number":\s*(\d+).*?"desired_input":\s*"(.*?)"'

    # Find all matches in the answer
    matches = re.findall(pattern, answer, re.DOTALL)

    # Convert matches to a list of tuples, with text_area_number as an integer
    return [(int(num), input_text) for num, input_text in matches]

def call_unified_task_clarifier(user_task, context, provider="anthropic"):
    with open('prompts/unified_task_clarifier_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'user_task': user_task,
        'context': context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    # print(prompt)
    answer = call_llm(prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    input(f"Unified task clarifier call")

    # Use regex to find the JSON array in the output
    json_match = re.search(r'\[.*]', answer, re.DOTALL)

    if json_match:
        json_str = json_match.group(0)

        try:
            questions = json.loads(json_str)

            # Verify that we have a list of strings
            if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                # 'questions' now contains the list of questions from the LLM's output
                return questions
            else:
                print("Unified Task Clarifier Error: Parsed JSON is not a list of strings")
                return []
        except json.JSONDecodeError:
            print("Unified Task Clarifier Error: Invalid JSON format")
            return []
    else:
        print("Unified Task Clarifier Error: No JSON array found in the output")
        return []


def call_unified_question_cleaner(user_task, user_qa, provider="anthropic"):
    with open('prompts/unified_question_cleaner_json.txt', 'r') as f:
        prompt = f.read()

    formatted_user_qa = ''

    for question, answer in user_qa:
        formatted_user_qa += 'Question: \n'
        formatted_user_qa += question.strip() + '\n'
        formatted_user_qa += 'Answer: \n'
        formatted_user_qa += answer.strip() + '\n'

    replacements = {
        'formatted_user_qa': formatted_user_qa,
        'user_task': user_task
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    
    answer = call_llm(prompt, provider='groq', model='llama-3.1-8b-instant')

    # Find JSON array in the text
    json_pattern = r'\[(?:[^[\]{}]|\{[^{}]*\})*\]'
    match = re.search(json_pattern, answer)

    if not match:
        raise ValueError("No JSON array found in the answer")

    json_str = match.group(0)

    # Parse JSON string
    try:
        parsed_json = json.loads(json_str)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON structure found in the answer")

    # Extract object-preference pairs
    object_preference_pairs = []
    for item in parsed_json:
        if isinstance(item, dict) and 'object' in item and 'preference' in item:
            object_preference_pairs.append((item['object'], item['preference']))

    return object_preference_pairs