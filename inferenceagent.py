import anthropic
import re
import os
import string
from utils.inference_data import *
from groq import Groq
from together import Together
import json
from openai import OpenAI
# Set up the Anthropic API client
anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# Set up the Groq API client
groq_client = Groq()

#set up Together API client
together_client = Together(api_key=os.environ.get('TOGETHER_API_KEY'))

#set up OpenAI API client
openai_client = OpenAI()

#system prompt is the part of the prompt that remains the same across calls to a given module, will attempt to cache if possible
def call_llm(system_prompt = '', user_prompt= '', provider="anthropic", model="claude-3-5-sonnet-20240620", max_tokens=2500):
    if provider == "anthropic":
        message = anthropic_client.beta.prompt_caching.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system = [
                {
                    "type": "text",
                    "text": system_prompt, 
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt
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
                    "content": user_prompt
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            stream=False,
            stop=None,
        )
        return completion.choices[0].message.content
    elif provider == "together":
        response = together_client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=0,
            top_p=1,
            top_k=50,
            repetition_penalty=1,
            stop=["<|eot_id|>"],
            stream=False,
        )
        return response.choices[0].message.content
    elif provider == 'openai':
        completion = openai_client.chat.completions.create(
            model="chatgpt-4o-latest",
            temperature=0,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )
        return completion.choices[0].message.content
    else:
        raise ValueError("Invalid provider. Choose 'anthropic', 'groq', or 'together'. ")

def call_action_agent(task, task_details, ax_tree, world_memory, action_memory, context, provider="openai"):
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i+1}) LOCATION: {lin_mem.object_details}\n{i+1}) EFFECT: {lin_mem.location_details}"
    with open('prompts/action_decider/action_decider_user.txt', 'r') as f:
        user_prompt = f.read()
    replacements = {
        'ax_tree': ax_tree,
        'task': task,
        'task_details': task_details,
        'world_memory': world_memory,
        'action_memory': new_action_memory,
    }
    user_prompt = string.Template(user_prompt)
    user_prompt = user_prompt.substitute(replacements)
    # print(user_prompt)
    
    with open('prompts/action_decider/action_decider_system.txt', 'r') as f:
        system_prompt = f.read()
    replacements = {
        'context' : context        
    }
    system_prompt = string.Template(system_prompt)
    system_prompt = system_prompt.substitute(replacements)
    # print(system_prompt)

    answer = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, provider=provider)
    
    print(answer)
    # input("Action call")

    pattern = r'choose\(\s*(\d+),\s*"([^"]*(?:\\.[^"]*)*)"\)'
    match = re.search(pattern, answer)

    if match:
        return (int(match.group(1)), match.group(2))

    return None

def call_memory_agent(web_agent_task, task_details, action_memory, world_memory, provider="anthropic"):
    new_action_memory = ''
    for i, lin_mem in enumerate(action_memory):
        new_action_memory += f"\n{i+1}) LOCATION: {lin_mem.object_details}\n{i+1}) EFFECT: {lin_mem.location_details}"
    # input("ACTION MEMORY")
    with open('prompts/world_mem_prompt_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
        'task_details': task_details,
        'world_memory': world_memory,
        'action_memory': new_action_memory,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    # print(prompt)
    
    answer = call_llm(user_prompt=prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    # input("World mem call")

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

def call_reflect_agent(action_number, reason_for_action, old_ax_tree, new_ax_tree, web_agent_task, task_details, provider="anthropic"):
    with open('prompts/reflect_store_prompt_json_v2.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'action_number': action_number,
        'reason_for_action': reason_for_action,
        'old_accessibility_tree': old_ax_tree,
        'new_accessibility_tree': new_ax_tree,
        'web_agent_task': web_agent_task,
        'task_details': task_details
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    # print(prompt)
    
    answer = call_llm(user_prompt=prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    # input("Memory store call")

    json_pattern = r'\{[^{}]*\}'

    # Find all matches
    json_match = re.findall(json_pattern, answer)
    if json_match:
        for match in json_match:
            json_str = match

            try:
                data = json.loads(json_str)
                if 'old_web_page_purpose' in data and 'action_effect' in data:
                    old_web_page_purpose = data.get('old_web_page_purpose', '')
                    action_effect = data.get('action_effect', '')
                    print(data)
                else:
                    continue
                return old_web_page_purpose, action_effect
            except json.JSONDecodeError:
                continue
    else:
        print("Reflect Restore Error: No JSON object found in the LLM output")
        return '', ''



def call_task_separator(web_agent_task, provider="anthropic"):
    with open('prompts/task_separator_prompt_json.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    
    answer = call_llm(user_prompt=prompt, provider='groq', model = 'llama-3.1-8b-instant')
    answer = answer.strip()
    print(answer)
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
            items = parsed_json.get('items', [])
            return items
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
    # print(prompt)
    
    answer = call_llm(user_prompt=prompt, provider='together')
    
    print(answer)
    # input("Task clarifier call")

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
    # print(prompt)
    
    answer = call_llm(user_prompt=prompt, provider='groq', model='llama-3.1-70b-versatile')

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
    answer = call_llm(user_prompt=prompt, provider = 'groq', model='llama-3.1-70b-versatile')
    
    print(answer)
    # input(f"Unified task clarifier call")

    # Use regex to find the JSON array in the output
    json_match = re.findall(r'\[.*?\]', answer, re.DOTALL)

    if json_match:
        for match in json_match:
            json_str = match

            try:
                questions = json.loads(json_str)

                # Verify that we have a list of strings
                if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                    # 'questions' now contains the list of questions from the LLM's output
                    return questions
                else:
                    # print("Unified Task Clarifier Error: Parsed JSON is not a list of strings")
                    # return []
                    continue
            except json.JSONDecodeError:
                continue
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
    # print(prompt)
    
    answer = call_llm(user_prompt=prompt, provider='groq', model='llama-3.1-8b-instant')

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