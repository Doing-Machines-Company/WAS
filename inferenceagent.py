import anthropic
import re
import os
import string
# Set up the Anthropic API client
client = anthropic.Anthropic(
    api_key =  os.environ.get("ANTHROPIC_API_KEY")
)

def call_action_agent(task, ax_tree, world_memory, action_memory, context):
    action_memory = str(action_memory)
    with open('prompts/new_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'ax_tree' : ax_tree,
        'task' : task,
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
    pattern = r'choose\((\d+)\)'

    # string = 'choose(0, "match this", "also match this")'
    print("Action call")
    input(answer[0].text)

    match = re.search(pattern, answer[0].text)

    if match:
        number = int(match.group(1))
        return number

    return None


def call_memory_agent(web_agent_task, action_memory, world_memory):
    action_memory = str(action_memory)
    with open('prompts/world_mem_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'web_agent_task': web_agent_task,
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
    print("World mem call")
    input(answer[0].text)

    match = re.search(pattern, answer[0].text)

    if match:
        return match.group(1).strip()

    print("NEW MEM EXTRACTION FAILED")

    return world_memory


def call_reflect_agent(action_number, old_ax_tree, new_ax_tree):
    with open('prompts/reflect_store_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'action_number': action_number,
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

    pattern = r'choose\(\s*"([^"]+)",\s*"([^"]+)"\)'
    # pattern = r'"""([\s\S]*?)"""'
    # string = 'choose(0, "match this", "also match this")'
    print("Memory store call")
    input(answer[0].text)

    match = re.search(pattern, answer[0].text)

    if match:
        return match.group(1), match.group(2)

    print("NEW MEM EXTRACTION FAILED")

    return None