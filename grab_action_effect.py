import anthropic
import os
import re

api_key = os.getenv('OPENAI_API_KEY')


client = anthropic.Anthropic(
    # defaults to os.environ.get("ANTHROPIC_API_KEY")
    api_key=api_key,
)



def extract_action_effect(before_image, after_image, action_info: str):
    prompts = [
        {
            "role": "user",
            "content": [
                {
                    "type": f"{action_info}",
                    "text": action_info
                },
                {
                    "type": "Screenshot of the page after the action:",
                    "text": action_info
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": before_image
                    }
                },
                {
                    "type": "text",
                    "text": "Screenshot of the page after the action:"
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": after_image
                    }
                },
                {
                    "type": "text",
                    "text": "\nIf the action succeeded, tell me what the effect of the action in the most general way possible.\nREMEMBER TO BE AS GENERAL AS POSSIBLE, DO NOT INCLUDE SPECIFICS. YOU MUST INCLUDE RELEVANT SPECIFIC AND CONCISE ORDERING DETAILS IF THERE IS ANY."
                }
            ]
        }
    ]
    system_prompt="You are an autonomous agent performing tasks for an user on a webshop. You are tasked with telling me what the effect of an action performed on a web page is, given the two screenshots of the web page before and after the action was performed. \n\nYour job is to label the button for all instances where it may occur, so you do not want to be specific with any details. You must use using general object types (like dates, products, numbers.etc), instead of specific instances of these objects (like June 24th, tweezers, 4). \nMention if there's a change in the purpose of the web page.\n\nBAD information:\n- Specific details.\n- Specific amounts or quantities.\n- Visual changes unless necessary to describe the effect of the action.\n\nThis is important: if the action was to change the option for a product, your final answer must be 'Changed variation of product'.\nThis is important: if there's a pattern or difference in the ordering of items (e.g., products/orders.etc) between two pages (e.g., one has older orders, or price has become descending), you must include this in your answer. You must note how the second page differs with regards to this pattern (e.g., cheaper items, older items). This ordering pattern is very important information. Ordering patterns only exist if all items on a page follow them.\n\nIf you are unsure of your answer, give as your answer '''NONE'''. If no major change occurred (e.g., action did nothing and there are no major or structural changes), or if the action failed, reply with '''NONE'''. \n\nFirst you must note the action that was performed. Then you must list the differences of the website before and after the action was performed. \n\nThen you must reason step by step through the two pages to determine any patterns in ordering.\n\nThen you must reason step by step for what the effect of the action was. Then with this action effect, you must then reason through all of the BAD information to remove all BAD information, leaving only the desired information for a concise description of the action effect.\n\nThen give a concise and assertive description of the action effect enclosed in ''', like this: \\n '''This is the difference between these two web page states'''. Do not include reasoning in your enclosed answer. You MUST first reason then give me your final answer in the specified format."

    message = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1500,
        temperature=0,
        system=system_prompt,
        messages=prompts
    )
    result = message.content[0]["content"]
    print(result)

    pattern = r"\'\'\'(.*?)\'\'\'"

    match = re.search(pattern, result, re.DOTALL)
    if match:
        final_answer = match.group(1).strip()
        return final_answer
    else:
        return None
