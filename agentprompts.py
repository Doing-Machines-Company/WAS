from openai import OpenAI
import os
import re

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

def get_interstate(intent, answers, model_name="gpt-4-1106-preview"):

    print(f"INTENT: {intent}")
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the intended goal."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. If you choose an answer, you must only choose a single answer. You only care about what is mentioned in each answer choice, the amount or emphasis of items in the list does not matter. Ignore any emphasis."},
        {"role": "system",
         "content": "Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. Try your best to choose an answer. After reasoning, give your final answer like this: \n '''1'''\n Or this: '''13'''."},
        {"role": "system",
         "content": "Here is an example of what your response should look like given their inputs."}
    ]
    print("INTERSTATE CHOICES")

    formatted_answers = '\n'.join(answers)
    print(formatted_answers)
    example_message = {
        "role": "system",
        "name": "example_user",
        "content": f"Task: How much does mature cheddar cost? \nChoose from these answers:\n 0) [View and buy red wine, white wine, whiskey, makeup, chicken, and dairy products] \n1) [View and buy clothing for men and children] \n2) [View and buy clothing for women, jewelry, and accessories] \n3) [View and buy beef, pork, milk and eggs] \n4) [View and buy seafood, poultry, and produce] \n5) [View account information and change account settings]"
    }
    messages.append(example_message)
    example_response = {
        "role": "system",
        "name": "example_assistant",
        "content": f"Let's reason through these possible answers step-by-step. \n- 1: This option mentions dairy products, and cheese is a type of dairy product. \n- 2: This option mentions nothing related to cheese. \n- 2: This option mentions nothing related to cheese. \n- 3: This option mentions milk, and milk are a type of dairy product. It however does not mention cheese. \n- 4: This option mentions poultry, and cheese is not a type of poultry. \n- 5: This option mentions nothing related to cheese. \nMature cheddar is a type of cheese. Even though option 0 mentions many functionalities, it mentions cheese, and option 3 only mentions milk and not other dairy products as a whole, the correct answer is '''0'''."
    }
    messages.append(example_response)

    example_message = {
        "role": "system",
        "name": "example_user",
        "content": f"Task: How much does milk cost? \nChoose from these answers:\n 0) [View and buy red wine, white wine, whiskey, makeup, chicken, and dairy products] \n1) [View and buy clothing for men and children] \n2) [View and buy clothing for women, jewelry, and accessories] \n3) [View and buy beef, pork, milk and eggs] \n4) [View and buy seafood, poultry, and produce] \n5) [View account information and change account settings]"
    }
    messages.append(example_message)
    example_response = {
        "role": "system",
        "name": "example_assistant",
        "content": f"Let's reason through these possible answers step-by-step. \n- 1: This option mentions dairy products, and cheese is a type of dairy product. \n- 2: This option mentions nothing related to cheese. \n- 2: This option mentions nothing related to cheese. \n- 3: This option mentions milk, and milk are a type of dairy product. It however does not mention cheese. \n- 4: This option mentions poultry, and cheese is not a type of poultry. \n- 5: This option mentions nothing related to cheese. \nMilk is a type of dairy, and option 0 contains dairy. However option 3 specifically mentions milk. Even though option 0 mentions mentions dairy, as option 3 mentions milk directly, I must choose the more specific choice and so I should choose option 3, the correct answer is '''0'''."
    }
    messages.append(example_response)

    messages.append({"role": "user",
        "content": f"Task: {intent}\nChoose from these answers:\n {formatted_answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0,
        max_tokens=1500,
        # top_p=0,
        seed=88888888
    )

    result = response.choices[0].message.content
    print(f"GPT RAW RETURN: {result}")

    pattern1 = r"\'\'\'(\d+)\'\'\'"
    pattern2 = r"\`\`\`(\d+)\`\`\`"

    match1 = re.search(pattern1, result, re.DOTALL)
    match2 = re.search(pattern2, result, re.DOTALL)

    if match1:
        final_answer = match1.group(1).strip()
        return final_answer
    elif match2:
        final_answer = match2.group(1).strip()
        return final_answer
    else:
        print("OH FUCK! ")
        return "FAILURE"


def get_intrastate(intent, answers, model_name="gpt-4-1106-preview"):

    print(f"INTENT: {intent}")
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task and multiple choice answers. Each answer represents an action being taken on the same web page. If the action has an effect description called ACTION EFFECT, pay attention to it. "},
        {"role": "system",
         "content": "If nothing in the answers I give you will help you achieve the task, or if you think that the task is impossible, return '''N/A'''. If there are multiple correct answers available, return '''N/A'''. The answer you need may not be currently visible to you, pay attention to ACTION EFFECTs that fit your task. "},
        {"role": "system",
         "content": "You want to first pay attention to all of effects labelled ACTION EFFECTS in each of the options I give you, especially paying attention to the effects of navigation related options. All dates are in the format of MM/DD/YY. YY is the last two digits of the year."},
        {"role": "system",
         "content": "Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. Pay close attention to options which let you view more information or navigate. Give the your final answer like this: \n '''1'''\n Or this: '''13'''. "},
    ]

    messages.append({"role": "user",
        "content": f"Task: {intent}\nChoose from these answers:\n {answers}"})

    response = client.chat.completions.create(
        # model=model_name,
        model="gpt-3.5-turbo-1106",
        messages=messages,
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
        final_answer = match1.group(1).strip()
        return final_answer
    elif match2:
        final_answer = match2.group(1).strip()
        return final_answer
    else:
        print("OH FUCK! ")
        return "FAILURE"