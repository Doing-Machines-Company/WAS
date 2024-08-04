import anthropic
import re
import os
import string
from utils.inference_data import *
# Set up the Anthropic API client
client = anthropic.Anthropic(
    api_key =  os.environ.get("ANTHROPIC_API_KEY")
)

def call_action_agent(task, task_details, ax_tree, world_memory, action_memory, context):
    action_memory = str(action_memory)
    with open('prompts/new_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'ax_tree' : ax_tree,
        'task' : task,
        'task_details': task_details,
        'world_memory': world_memory,
        'action_memory' : action_memory,
        'context' : context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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
    

    answer = message.content
    # match = re.search(r"choose\((\d+)\)", answer[0].text)

    # pattern = r'choose\((\d+),\s*"([^"]+)",\s*"([^"]+)"\)'
    # pattern = r'choose\((\d+),\s*"((?:\\.|[^\\"])*)",\s*"((?:\\.|[^\\"])*)"'
    # pattern = r'choose\((\d+)\)'
    pattern = r'choose\(\s*(\d+),\s*"([^"]*(?:\\.[^"]*)*)"\)'

    # string = 'choose(0, "match this", "also match this")'

    print(answer[0].text)
    input("Action call")

    match = re.search(pattern, answer[0].text)

    if match:
        return (int(match.group(1)), match.group(2))

    return None


def call_memory_agent(web_agent_task, task_details, action_memory, world_memory):
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
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content
    # match = re.search(r"choose\((\d+)\)", answer[0].text)

    # pattern = r'choose\((\d+),\s*"([^"]+)",\s*"([^"]+)"\)'
    pattern = r'"""([\s\S]*?)"""'
    # string = 'choose(0, "match this", "also match this")'

    print(answer[0].text)
    input("World mem call")

    match = re.search(pattern, answer[0].text)

    if match:
        return match.group(1).strip()

    print("NEW MEM EXTRACTION FAILED")

    return world_memory


def call_reflect_agent(action_number, reason_for_action, old_ax_tree, new_ax_tree):
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
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content
    # match = re.search(r"choose\((\d+)\)", answer[0].text)

    # pattern = r'choose\(\s*"([^"]+)",\s*"([^"]+)"\)'
    pattern = r'choose\(\s*"([^\"]*(?:\\.[^\"]*)*)",\s*"([^\"]*(?:\\.[^\"]*)*)"'
    # pattern = r'"""([\s\S]*?)"""'
    # string = 'choose(0, "match this", "also match this")'

    print(answer[0].text)
    input("Memory store call")

    match = re.search(pattern, answer[0].text)

    if match:
        return match.group(1), match.group(2)

    print("REFLECTION FAILED")

    return None

def call_task_separator(web_agent_task):
    with open('prompts/task_separator_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content
    # match = re.search(r"choose\((\d+)\)", answer[0].text)

    # pattern = r'choose\((\d+),\s*"([^"]+)",\s*"([^"]+)"\)'
    # string = 'choose(0, "match this", "also match this")'
    answer = answer[0].text.strip()
    match = re.search(r'`(.*?)`', answer)
    if match:
        return match.group(1).split(',')
    else:
        return []

    # def extract_list_from_string(s):
    #     # Define the regex pattern to match a list of strings
    #     pattern = r'\["(.*?)"\]'

    #     # Use re.findall to find all matches of the pattern in the string
    #     match = re.search(pattern, s)

    #     if match:
    #         # Extract the list of strings from the match
    #         list_of_strings = [x.strip() for x in match.group(1).split('", "')]
    #         return list_of_strings
    #     else:
    #         return []
    
    # items_of_interest = re.findall(r"'([^']*)'", answer)

    # print(answer)
    # input("Task separator call")
    #
    #
    # return items_of_interest


def call_task_clarifier(user_task, item_context_pairs):
    with open('prompts/task_parser_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'user_task': user_task,
        'item_of_interest': item_of_interest,
        'context': context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    print(prompt)
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content

    pattern = r'"""([\s\S]*?)"""'
    # string = 'choose(0, "match this", "also match this")'

    print(answer[0].text)
    input("Task clarifier call")

    match = re.search(pattern, answer[0].text)

    if match:
        return match.group(1).strip()

    return ""


def call_input_agent(user_task, agent_intent, task_details, input_ax_tree, context, hidden_inputs: list[HiddenInput]):
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
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content


    print(answer[0].text)
    input(f"All input call given intent {agent_intent}")

    # pattern = r'choose\((\d+),\s*[\'"](.+?)[\'"]\)' doesn't match to empty string
    pattern = r'choose\((\d+),\s*[\'"](.*)[\'"]\)'

    matches = re.findall(pattern, answer[0].text)


    return [(int(i), s) for i, s in matches]


def call_unified_task_clarifier(user_task, context):
    with open('prompts/unified_task_clarifier.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'user_task': user_task,
        'context': context
    }
    prompt = string.Template(prompt)
    prompt = prompt.substitute(replacements)
    # print(prompt)
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content


    print(answer[0].text)
    input(f"Unified task clarifier call")

    pattern = r'"""([\s\S]*?)"""'
    matches = re.findall(pattern, answer[0].text)

    return [question.strip() for question in matches if question.strip() !='']


def call_unified_question_cleaner(user_task, user_qa):
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
    message = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
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

    answer = message.content
    # match = re.search(r"choose\((\d+)\)", answer[0].text)

    # pattern = r'choose\(\s*"([^"]+)",\s*"([^"]+)"\)'
    pattern = r'choose\(\s*"([^\"]*(?:\\.[^\"]*)*)",\s*"([^\"]*(?:\\.[^\"]*)*)"'
    # pattern = r'"""([\s\S]*?)"""'
    # string = 'choose(0, "match this", "also match this")'

    print(answer[0].text)
    input("Question cleaner call")

    matches = re.findall(pattern, answer[0].text)

    return matches