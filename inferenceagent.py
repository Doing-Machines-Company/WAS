import anthropic
import re
import os

# Set up the Anthropic API client
client = anthropic.Anthropic(
    api_key =  os.environ.get("ANTHROPIC_API_KEY")
)

def call_agent(task, ax_tree):
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
                        "text": f"You are an AI web agent tasked with navigating websites and performing actions based on given instructions. Your goal is to analyze the provided accessibility tree of a website and choose the most appropriate action to complete a given task.\n\nHere's the task you need to complete:\n<task>\n{task}\n</task>\n\nYou will be provided with a labeled accessibility tree of a website. Each actionable item in the tree starts with a number in square brackets, like this: [0]. Some actions may have additional information about their function in curly brackets at the end, like this: [0] Some action " + "{This action does this}" + f"\n\nHere's the accessibility tree of the current page:\n<accessibility_tree>\n{ax_tree}\n</accessibility_tree>\n\nTo complete this task, follow these steps:\n\n1. Analyze the page:\n   - Carefully read through the accessibility tree.\n   - Identify the main elements and actions available on the page.\n   - Summarize what the page does in a brief paragraph.\n\n2. Understand the task:\n   - Review the given task and identify what needs to be accomplished.\n   - Determine which actions on the page are relevant to completing the task.\n\n3. Plan your next action:\n   - Based on your analysis of the page and the task, decide on the most appropriate next action.\n   - Reason step-by-step to explain why you've chosen this action.\n\n4. Choose the action:\n   - Select the number corresponding to your chosen action from the accessibility tree.\n   - Use the python function choose(action: int) to indicate your selection.\n\nYour response should be structured as follows:\n\n<page_analysis>\n[Provide a brief summary of what the page does based on the accessibility tree]\n</page_analysis>\n\n<task_analysis>\n[Explain your understanding of the task and what needs to be done]\n</task_analysis>\n\n<action_reasoning>\n[Provide step-by-step reasoning for your chosen action]\n</action_reasoning>\n\n<action_selection>\n[Use the choose() function to select your action]\n</action_selection>\n\nRemember to base your decision solely on the information provided in the accessibility tree and the given task. Do not assume or infer any additional functionality that is not explicitly stated. If you cannot complete the task with the available actions, explain why and choose the most relevant action if possible.\n\nBegin your analysis and action selection now."
                    }
                ]
            }
        ]
    )

    answer = message.content
    match = re.search(r"choose\((\d+)\)", answer[0].text)
    print(answer[0].text)

    if match:
        return int(match.group(1))
    else:
        return -1