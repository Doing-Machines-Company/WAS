from impls import *
from ax_tree_process import *
from drivers import *

def construct_url_prompt(intent: str, new_obs: AxObservation, model_name: str) -> str: # TODO, ignored for now
    pass

def construct_elements_prompt(intent: str, cur_obs: AxObservation, model_name: str) -> (str, list[Action]): # MOSTLY FOR GPT
    if model_name.startswith('gpt'):
        cleaned_tree, action_list = process_axtree_action(cur_obs)
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

def construct_memory_prompt(intent: str, last_action: Action, old_obs: AxObservation, new_obs: AxObservation, model_name: str) -> str: # NOT NEEDED FOR MemGPT
    if model_name.startswith('gpt'):
        messages = [{"role": "system",
                     "content": f"You are an evaluator for an autonomous agent performing tasks for an user on a webshop. I am going to give you a task, the last action performed on the webshop, and two accessibility trees. The first accessibility tree is the previous state of the webpage, and the second accessibility tree is the current state of the webpage. "},
                    {"role": "system",
                     "content": f"First look at the task, then you must generate subtasks that can help you complete this task, reasong through these step-by-step. If any of the information in only the new accessibility tree is relevant to the task, that is a INFORMATION MEMORY you want to reply with. Then look at the last action performed, if the two accessibility trees indicates that the action was successful and the action helps you complete the task or helps you complete a subtask, the task or subtask completed is the TASK MEMORY you want to reply with. For the TASK MEMORY, include only a brief summary of only the task or subtask completed. "},
                    {"role": "system",
                     "content": "Give your final reply in the form '''info mem reply you want|task mem reply you want''', where | is used to delimit the information memory and task memory you want to reply with. If you don't want to store a field, just reply with that side empty. Remember to enclose your final reply with '''."}
                    ]
        old_tree_cleaned, new_tree_cleaned = process_axtree_memory(old_obs, new_obs)
        messages.append({"role": "user", f"content": f"Intended task: {intent}\nLast action performed: {last_action}\nOld accessibility tree: \n'''\n {old_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"})


        return messages
    return ''