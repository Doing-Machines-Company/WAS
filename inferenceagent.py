import anthropic
import re
import os

# Set up the Anthropic API client
client = anthropic.Anthropic(
    api_key =  os.environ.get("ANTHROPIC_API_KEY")
)

def call_agent(task, ax_tree, memory):
    memory = str(memory)
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
                        "text": f"You are a web agent tasked with navigating a website to complete a specific task. You will be provided with an accessibility tree, a task to complete, and a memory of actions you've taken so far. Your goal is to analyze the current web page, reason about your task and past actions, and choose the most appropriate next action to complete your task.\n\nHere's the accessibility tree of the current web page:\n<accessibility_tree>\nf{ax_tree}\n</accessibility_tree>\n\nYour task is:\n<task>\nf{task}\n</task>\n\nHere's the memory of actions you've taken so far:\n<action_memory>\nf{memory}\n</action_memory>\n\nFollow these steps to complete your task:\n\n1. Analyze the web page:\n   - Examine the accessibility tree carefully.\n   - Understand the purpose and functionality of the current web page.\n   - Note any relevant elements or actions available on the page.\n\n2. Reason about your task and past actions:\n   - Review your assigned task and consider what steps are necessary to complete it.\n   - Examine your action memory to understand what you've already done.\n   - Determine if there is a clear sign that the last action failed.\n   - Determine what needs to be done next to progress towards your goal.\n\n3. Choose the next action:\n   - Based on your analysis and reasoning, identify the most appropriate action from the accessibility tree.\n   - Consider how this action will help you progress towards completing your task.\n   - Ensure the chosen action aligns with your current position in the task sequence.\n\n4. Provide your decision:\n   - Use the following Python function format to indicate your chosen action:\n     choose(action_number: int, current_web_page_purpose: str, object_action_acts_on: str)\n   - action_number: The number of the action you've chosen from the accessibility tree.\n   - current_web_page_purpose: A brief description of the current web page's purpose.\n   - object_action_acts_on: The specific object or element the action will affect.\n\nRemember:\n- Every action in the accessibility tree is labeled with a number at the start of the line.\n- Some actions have " + "{}" + " brackets at the end of the line describing what that action does. Assume these descriptions are accurate.\n- The action memory is a list of tuples in the format: (Where the action was taken, the effect of that action, the object that action was taken on).\n- More recent actions in the memory are closer to the right of the list.\n\nFollow the steps carefully and reason step-by-step, then give your final answer inside a Python function as described above. "
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