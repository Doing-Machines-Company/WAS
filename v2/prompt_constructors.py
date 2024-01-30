from impls import *
from ax_tree_process import process_axtree

def construct_url_prompt(intent: str, new_obs: PageObservation, model_name: str) -> str: # TODO, ignored for now
    pass

def construct_elements_prompt(intent: str, cur_obs: PageObservation, model_name: str) -> (str, list[Action]): # MOSTLY FOR GPT
    if model_name.startswith('gpt'):
        cleaned_tree, action_list = process_axtree(cur_obs)
        messages = [
            {"role": "system",
             "content": "You are an autonomous agent performing tasks for an user on a webshop. I am going to give you a task, and an accessibility tree. Some lines are labelled with a number, these lines are actions you can choose, you must choose one action from the accessibility tree that is labeled with a number. All actions labelled with numbers in square brackets can be completed. "},
            {"role": "system",
             "content": "The accessibility tree is reflective of the layout of the webpage. Only actions starting with a number enclosed in brackets, like [96], are available action choices. Infer from the text of each line what that action does. "},
            {"role": "system",
             "content": "First look at the available action choices, then generate subtasks, using the available options as subtasks when they are relevant. Then reason through every single possible action I give you step-by-step thoughtfully. Do your best to choose an answer. You must return your final answer as a number and a colon enclosed in ''', like '''102:''' if the final action you choose is the line on the accessibility tree starting with [102]. If the final action you choose is an action with input, you must also reply with what you wish to input into that option, like '''102:something''', and it will be inputted for that action. "}]



        messages.append({"role": "user", f"content": f"This is your task: {intent}\nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})


        return messages, action_list
    return ''

def construct_memory_prompt(intent: str, old_tree: str, new_tree: str, model_name: str) -> str: # NOT NEEDED FOR MemGPT
    if model_name.startswith('gpt'):
        messages = []

        messages.append({"role": "user",
                         f"content": f""})

        return ''
    return ''