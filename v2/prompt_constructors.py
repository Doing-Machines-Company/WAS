from impls import *

def construct_url_prompt(new_obs: PageObservation, model_name: str) -> str: # TODO, ignored for now
    pass

def construct_elements_prompt(new_obs: PageObservation, model_name: str) -> str: # MOSTLY FOR GPT
    if model_name.startswith('gpt'):
        cleaned_tree = ""
        counter = 0
        messages = [
            {"role": "system",
             "content": "You are an autonomous agent performing tasks for an user on a webshop. I am going to give you a task, and an accessibility tree. Some lines are labelled with a number, these lines are actions you can choose, you must choose one action from the accessibility tree that is labeled with a number."},
            {"role": "system",
             "content": "The accessibility tree is reflective of the layout of the webpage. Only actions starting with a number enclosed in brackets, like [96], are available action choices. Infer from the text of each line what that action does. "},
            {"role": "system",
             "content": "First look at the available action choices, then generate subtasks, using the available options as subtasks when they are relevant. Then reason through every single possible action I give you step-by-step thoughtfully. Do your best to choose an answer. You must return your final answer as a number enclosed in ''', like '''102''' if the final action you choose is the line on the accessibility tree starting with [102]."}]

        for i in range(len(new_obs.nodes_info)):
            print(f"{new_obs.nodes_info[i]['indent']}{new_obs.nodes_info[i]['role']}: {new_obs.nodes_info[i]['name']}")

        exit()

        messages.append({"role": "user", f"content": f"What is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})


        return messages
    return ''

def construct_memory_prompt(new_obs: PageObservation, model_name: str) -> str: # NOT NEEDED FOR MemGPT
    pass