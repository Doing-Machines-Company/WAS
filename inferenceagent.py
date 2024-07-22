import anthropic
import re
import os
import string
# Set up the Anthropic API client
client = anthropic.Anthropic(
    api_key =  os.environ.get("ANTHROPIC_API_KEY")
)

def call_agent(task, ax_tree, memory, context):
    memory = str(memory)
    with open('prompts/new_prompt.txt', 'r') as f:
        prompt = f.read()
    replacements = {
        'ax_tree' : ax_tree,
        'task' : task, 
        'memory' : memory,
        'context' : context
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

    pattern = r'choose\((\d+),\s*"([^"]+)",\s*"([^"]+)"\)'

    # string = 'choose(0, "match this", "also match this")'
    print(answer[0].text)

    match = re.search(pattern, answer[0].text)

    if match:
        number = int(match.group(1))
        string1 = match.group(2)
        string2 = match.group(3)
        return number, string1, string2

    return None