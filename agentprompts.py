from openai import OpenAI
import os
import re
import json
from llama_cpp import Llama


api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

with open('agentprompts_fewshot.json', 'r') as file:
    agentprompts = json.load(file)





def interstate_filter(intent, choice):
    llm = Llama(model_path="./mistral-7b-instruct-v0.2.Q5_K_M.gguf",
                chat_format="llama-2")  # Set chat_format according to the model you are using

    messages = [
        {"role": "system",
         "content": "You are an assitant tasked with filtering out irrelevant information for an user on a website by doing Question and Answer tasks. I am going to give you a task, and a list of functionalities for a web page. "},
        {"role": "system",
         "content": "Tell me if this list of functionalities can help me accomplish the task. "},
        {"role": "system",
         "content": "Reason through every single option I give you step-by-step thoughtfully. Your final reply can only be '''YES''' or '''NO'''."},
        {"role": "user",
         "content": f"Task: Buy milk\nFunctionalities: [Change password, change email, change address, view eggs, view chicken, view dairy]"},
        {"role": "assistant",
         "content": "The user needs to buy milk. Milk is a dairy. This option allows me to view dairy. So hence my final answer is: \n'''YES'''."},
        {"role": "user",
         "content": f"Task: Sign up for newsletter\nFunctionalities: [Change password, change email, change address, view eggs, view chicken, view dairy]"},
        {"role": "assistant",
         "content": "While account options are mentioned in this list of functionalities, the newsletter is not mentioned. So hence my final answer is: \n'''NO'''."},
        {"role": "user",
         "content": f"Task: {intent}\nFunctionalities: {choice}"}
    ]

    output = llm.create_chat_completion(messages=messages, temperature=0.0)
    print("RAW OUT")
    print(output['choices'][0]['message']['content'])
    return output['choices'][0]['message']['content']


def get_interstate_instruct(intent, answers):
    interstate_shots = agentprompts["interstate"]
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the intended goal."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. If you choose an answer, you must only choose a single answer. You only care about what is mentioned in each answer choice. Do your best to choose an answer."},
        {"role": "system",
         "content": "First generate subtasks to complete the task using only options available to you. Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may or may not align to completing the task or a subtask. After reasoning, give your final answer like this: \n '''answer'''."},
        {"role": "system",
         "content": "Here is a few example of what your response should look like given their inputs."}]

    for prompts in interstate_shots:
        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Task: {prompts['intent']} \nChoose from these possible answers:\n {prompts['question']}"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_agent",
            "content": prompts['answer']
        }
        messages.append(example_response)

        formatted_answers = '\n'.join(answers)
        print(formatted_answers)

        messages.append({"role": "user",
                         "content": f"Now here's your actual task. \nTask: {intent}\nChoose from these answers:\n {formatted_answers}"})

        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",
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


def get_interstate(intent, answers, model_name="gpt-4-1106-preview"):
    interstate_shots = agentprompts["interstate"]

    print(f"INTENT: {intent}")
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the intended goal, or is needed or contains information to help you achieve your goal. "},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. If you choose an answer, you must only choose a single answer. If there are multiple possible answers, you must choose one. You only care about what is mentioned in each answer choice, the amount or emphasis of items in the list does not matter. Ignore any emphasis."},
        {"role": "system",
         "content": "YOU MUST reason through EVERY SINGLE option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. YOU MUST try your best to choose an answer. If one option may lead to more information or something to help you complete your task, it is a valid choice. After reasoning, give your final answer like this: \n '''1'''\n Or this: '''13'''."},
        {"role": "system",
         "content": "Here are a few examples of what your response should look like given their inputs."}
    ]
    print("INTERSTATE CHOICES")

    for prompts in interstate_shots:
        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Task: {prompts['intent']} \nChoose from these possible answers:\n {prompts['question']}"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_agent",
            "content": prompts['answer']
        }
        messages.append(example_response)


    formatted_answers = '\n'.join(answers)
    print(formatted_answers)

    messages.append({"role": "user",
                     "name": "user",
        "content": f"Now here's your actual task. \nTask: {intent}\nChoose from these answers:\n {formatted_answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0,
        max_tokens=3000,
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

def should_search(intent):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop given a specific task. I am going to you give the task the user wants to complete, and you are to evaluate whether or not the web shop's search bar should be used. The search bar is only used for searching for products you need to buy. "},
        {"role": "system",
         "content": "You only care about whether or not the search bar of the website should be used. Reason through your answer step-by-step, and give your final answer as '''YES''' or '''NO'''. GIVE ONLY ONE OF THESE AS YOUR FINAL ANSWER AFTER REASONING. "},
        {"role": "system",
         "content": "Here are a few examples of what your response should look like given their inputs."},
        {
            "role": "system",
            "name": "example_user",
            "content": "find my last order with chocolate milk"
        },
        {
            "role": "system",
            "name": "example_agent",
            "content": "I need to find an order, orders are not products you can buy on a web shop. Therefore I should not use the search bar. My final answer is: \n'''NO'''"
        },
        {
            "role": "system",
            "name": "example_user",
            "content": "find truffle flavoured ice cream"
        },
        {
            "role": "system",
            "name": "example_agent",
            "content": "I need to find a type of ice cream, ice cream are a product that you may be able to buy on a web shop. Therefore I should use the search bar. My final answer is: \n'''YES'''"
        },
        {"role": "user",
         "content": f"Now here is your actual task. \nTask: {intent}"}
    ]

    response = client.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0,
        max_tokens=1500,
        seed=88888888
    )

    result = response.choices[0].message.content
    if 'YES' in result:
        return 'YES'
    else:
        return 'NO'

def get_intrastate_full(intent, answers, page_desc, model_name="gpt-4-1106-preview"):

    intrastate_shots = agentprompts["intrastate"]
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task and multiple choice answers. Each answer represents an action being taken on the same web page. If the action has an effect description called ACTION EFFECT, pay attention to it. You want to choose the action effect which will help you find the most optimal answer, which you may not currently see. "},
        {"role": "system",
         "content": "If nothing in the answers I give you will help you achieve the task, or if you think that the task is impossible, return '''STOP'''. If there are multiple correct answers available, return '''STOP'''. The answer you need may not be currently visible to you, pay attention to ACTION EFFECTs that fit your task. "},
        {"role": "system",
         "content": "You want to first pay attention to all of effects labelled ACTION EFFECTS in each of the options I give you, especially paying attention to the effects of navigation related options. All dates are in the format of MM/DD/YY. YY is the last two digits of the year. If there is EXTRA INFORMATION, pay attention to it, as it may provide more context for the ACTION EFFECT. "},
        {"role": "system",
         "content": "First generate subtasks to complete the task using only options available to you. Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may or may not align to completing the task or a subtask. Pay close attention to options which let you view more information or navigate. Give the your final answer like this: \n '''1'''\n Or this: '''13'''. "},
        {"role": "system",
         "content": "If you think that the task has been completed, and all possible subtasks have been complete, return '''STOP'''. Pay attention to what the current page's description, if the task requires you to find something or retrieve information and you are on the correct page, for example, finish with '''STOP:INFORMATION YOU RETRIEVED''' to retrieve information and stop, or '''4:INFORMATION YOU RETRIEVED''' to retrieve information and perform action 4. If you think that MULTIPLE ACTIONS are required in a sequence to complete the task, YOU MUST CHOOSE the first action in that sequence. "},
        {"role": "system",
         "content": "Here is are a few examples of what your response should look like given their inputs: \n"}
    ]

    for prompts in intrastate_shots:
        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Task: {prompts['intent']} \nPage information: '''\n{prompts['desc']}'''\n\nChoose from these possible answers:\n {prompts['question']}"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_agent",
            "content": prompts['answer']
        }
        messages.append(example_response)
    messages.append({"role": "user",
        "content": f"Now here is your actual task. \nTask: {intent}\nPage description: {page_desc}\nChoose from these answers:\n{answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0,
        max_tokens=1500,
        # top_p=0,
        seed=12345678
    )

    result = response.choices[0].message.content
    print(f"GPT RAW RETURN: {result}")

    pattern1 = r"\'\'\'STOP:([A-Za-z0-9]+)\'\'\'"
    pattern2 = r"\'\'\'(\d+):([A-Za-z0-9]+)\'\'\'"
    pattern3 = r"\'\'\'(\d+)\'\'\'"


    match1 = re.search(pattern1, result, re.DOTALL)
    match2 = re.search(pattern2, result, re.DOTALL)
    match3 = re.search(pattern3, result, re.DOTALL)

    if match1:
        return (-1, match1.group(1).strip())
    elif match2:
        return (match2.group(1).strip(), match2.group(2).strip())
    elif match3:
        return (match3.group(1).strip(), "")
    else:
        return (-1, "")

def get_intrastate(intent, answers, current_tree, model_name="gpt-4-1106-preview"):
    print("CURR TREE")
    print(current_tree)
    input("CONTINUE")

    intrastate_shots = agentprompts["intrastate"]
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task and multiple choice answers. Each answer represents an action being taken on the same web page. If the action has an effect description called ACTION EFFECT, pay attention to it. You want to choose the action effect which will help you find the most optimal answer, which you may not currently see. "},
        {"role": "system",
         "content": "If nothing in the answers I give you will help you achieve the task, or if you think that the task is impossible, return '''N/A'''. If there are multiple correct answers available, return '''N/A'''. The answer you need may not be currently visible to you, pay attention to ACTION EFFECTs that fit your task. "},
        {"role": "system",
         "content": "You want to first pay attention to all of effects labelled ACTION EFFECTS in each of the options I give you, especially paying attention to the effects of navigation related options. All dates are in the format of MM/DD/YY. YY is the last two digits of the year. "},
        {"role": "system",
         "content": "Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. Pay close attention to options which let you view more information or navigate. Give the your final answer like this: \n '''1'''\n Or this: '''13'''. "},
        {"role": "system",
         "content": "Here is are a few examples of what your response should look like given their inputs: \n"}
    ]

    for prompts in intrastate_shots:
        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Task: {prompts['intent']} \nCurrent page accessibility tree: N/A\nChoose from these possible answers:\n {prompts['question']}"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_agent",
            "content": prompts['answer']
        }
        messages.append(example_response)
    messages.append({"role": "user",
        "content": f"Now here is your actual task. \nTask: {intent}\nChoose from these answers:\n {answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
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

def use_gpt_fill_input(tree_str, specific_html, user_context):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop. You are tasked with analyzing a web page based on the entire page's accessibility tree and one element's specific HTML."},
        {"role": "system",
         "content": "The HTML will represent an element that you must input some text into."},
        {"role": "system",
         "content": "The accessibility tree will be a string representation of the accessibility tree of the web page."},
        {"role": "system",
         "content": "You will also be given some context about the user, which will be a dictionary of information about the user."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, use '''N/A''' as the input."},
        {"role": "system",
         "content": "Reason through your answer, then give the exact string you would input into the box enclosed by '''s, like this: \n '''I would input this string'''. Do not include reasoning in your enclosed answer."},
        {"role": "user",
        "content": f"Here's the information, what should be input into the element represented by the specific HTML? \nSpecific element HTML: {specific_html}\nCurrent page accessibility tree:\n{tree_str}\nUser intent: {user_context}\n"}
    ]

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0.0,
        max_tokens=400
    )

    result = response.choices[0].message.content

    pattern = r"\'\'\'(.*?)\'\'\'"

    match = re.search(pattern, result, re.DOTALL)
    # # print(f"RESULT: {result}")
    if match:
        final_answer = match.group(1).strip()
        return final_answer
    else:
        return "FAILURE"

    return "FAILURE"


def get_intrastate_type(intent, answers, model_name="gpt-4-1106-preview"):
    type_shots = agentprompts["intrastate_type"]
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. You have already found the all objects you need to complete the task, so right now you need to choose the type of action you wish to perform on that object. I am going to give you a task and multiple choice answers. Each answer is a type of action, choose the type which will help you complete the task. If the action type has an effect description called ACTION EFFECT, pay attention to it. "},
        {"role": "system",
         "content": "If nothing in the answers I give you will help you achieve the task, or if you think that the task is impossible, return '''N/A'''. If there are multiple correct answers available, return '''N/A'''. "},
        {"role": "system",
         "content": "You want to first pay attention to all of effects labelled ACTION EFFECTS in each of the options I give you, especially paying attention to the effects of navigation related options. REMEMBER, ANSWER THE QUESTION AS IF YOU HAVE FOUND EVERYTHING YOU ARE LOOKING FOR AND NEED NO FURTHER NAVIGATION."},
        {"role": "system",
         "content": "Reason through every single option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. Pay close attention to options which let you view more information or navigate. Give the your final answer like this: \n '''1'''\n Or this: '''13'''. "},
        {"role": "system",
         "content": "Here is a example of what your response should look like given their inputs: \n"}
    ]

    for prompts in type_shots:
        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Task: {prompts['intent']} \nChoose from these possible answers:\n {prompts['question']}"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_agent",
            "content": prompts['answer']
        }
        messages.append(example_response)

    messages.append({"role": "user",
        "content": f"Now here is your actual task. \nTask: {intent}\nChoose from these answers:\n {answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
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
