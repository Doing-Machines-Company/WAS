import anthropic
import re
import os
import string
from utils.inference_data import *
from groq import Groq

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
    with open('prompts/world_mem_prompt_new.txt', 'r') as f:
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
    
    answer = call_llm(prompt, provider)
    
    print(answer)
    input("World mem call")

    pattern = r'"""([\s\S]*?)"""'
    match = re.search(pattern, answer)

    if match:
        return match.group(1).strip()

    print("NEW MEM EXTRACTION FAILED")
    return world_memory

def call_reflect_agent(action_number, reason_for_action, old_ax_tree, new_ax_tree, provider="anthropic"):
    with open('prompts/reflect_store_prompt.txt', 'r') as f:
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
    
    answer = call_llm(prompt, provider)
    
    print(answer)
    input("Memory store call")

    pattern = r'choose\(\s*"([^\"]*(?:\\.[^\"]*)*)",\s*"([^\"]*(?:\\.[^\"]*)*)"'
    match = re.search(pattern, answer)

    if match:
        return match.group(1), match.group(2)

    print("REFLECTION FAILED")
    return None

def call_task_separator(web_agent_task, provider="anthropic"):
    with open('prompts/task_separator_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    
    answer = call_llm(prompt, provider='groq', model = 'llama-3.1-8b-instant')
    answer = answer.strip()
    match = re.search(r'`(.*?)`', answer)
    if match:
        return match.group(1).split(',')
    else:
        return []

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
    with open('prompts/mass_input_prompt.txt', 'r') as f:
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
    
    print(answer)
    input(f"All input call given intent {agent_intent}")

    pattern = r'choose\((\d+),\s*[\'"](.*)[\'"]\)'
    matches = re.findall(pattern, answer)

    return [(int(i), s) for i, s in matches]

def call_unified_task_clarifier(user_task, context, provider="anthropic"):
    with open('prompts/unified_task_clarifier.txt', 'r') as f:
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

    pattern = r'"""([\s\S]*?)"""'
    matches = re.findall(pattern, answer)

    return [question.strip() for question in matches if question.strip() !='']

def call_unified_question_cleaner(user_task, user_qa, provider="anthropic"):
    with open('prompts/unified_question_cleaner.txt', 'r') as f:
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
    
    print(answer)
    input("Question cleaner call")

    pattern = r'choose\(\s*"([^\"]*(?:\\.[^\"]*)*)",\s*"([^\"]*(?:\\.[^\"]*)*)"'
    matches = re.findall(pattern, answer)

    return matches