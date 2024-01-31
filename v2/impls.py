from __future__ import annotations
from models import *
from typing import Any, Optional, Union
from drivers import *
from call_llm import *
from typing import Optional
from action import Action
from enum import Enum, auto
from typing import Optional



class Phase(Enum):
    CHOOSING_URL = auto()
    CHOOSING_ELEMENTS = auto()
    # HANDLING_MEMORY = auto()

class BaseAgent(Agent):

    def __init__(self, intent: str):
        self.intent = intent
        self.last_action = None
        self.old_obs = None
        self.phase = Phase.CHOOSING_ELEMENTS # or 'choosing_elements' (or 'handling_memory') # TODO MAKE ENUM TYPE

        self.task_memory = []  #
        self.info_memory = []  # should really only need to remember information that needs to be synthesised
        self.environmental_changes = dict()

    def construct_url_prompt(self, intent: str, new_obs: AxObservation, model_name: str) -> str:  # TODO, ignored for now
        pass

    def construct_elements_prompt(self, intent: str, cur_obs: AxObservation, model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT
        if model_name.startswith('gpt'):
            cleaned_tree, action_list = self.process_axtree_action(cur_obs)
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. I am going to give you a task, and an accessibility tree. Some lines are labelled with a number, these lines are actions you can choose, you must choose one action from the accessibility tree that is labeled with a number. All actions labelled with numbers in square brackets can be completed. "},
                {"role": "system",
                 "content": "The accessibility tree is reflective of the layout of the webpage. Only actions starting with a number enclosed in brackets, like [96], are available action choices. Infer from the text of each line what that action does. "},
                {"role": "system",
                 "content": "First look at the available action choices, then generate subtasks, using the available options as subtasks when they are relevant. Then reason through every single possible action I give you step-by-step thoughtfully. Do your best to choose an answer. You must return your final answer as a number and a colon enclosed in ''', like '''102:''' if the final action you choose is the line on the accessibility tree starting with [102]. If the final action you choose is an action with input, you must also reply with what you wish to input into that option, like '''102:something''', and it will be inputted for that action. "}]

            messages.append({"role": "user",
                             f"content": f"This is your task: {intent}\nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})

            return messages, action_list
        return ''

    def construct_memory_prompt(self, intent: str, last_action: Action, old_obs: AxObservation, new_obs: AxObservation,
                                model_name: str) -> str:  # NOT NEEDED FOR MemGPT
        if model_name.startswith('gpt'):
            messages = [{"role": "system",
                         "content": f"You are an evaluator for an autonomous agent performing tasks for an user on a webshop. I am going to give you a task, the last action performed on the webshop, and two accessibility trees. The first accessibility tree is the previous state of the webpage, and the second accessibility tree is the current state of the webpage. "},
                        {"role": "system",
                         "content": "A IMPORTANT SUBTASK is a subtask that is essential to the completion of a task. For example if a task was adding a list of items to the cart, then adding an item on the list to cart would be an IMPORTANT SUBTASK, while clicking on a link to a different page would be an UNIMPORTANT SUBTASK, as clicking on a link is not essential to completing this example task. Any subtasks that involve discovery or navigation are UNIMPORTANT. "},
                        {"role": "system",
                         "content": f"First look at the task, then you must generate subtasks that can help you complete this task, reasong through these step-by-step. If any of the information in only the new accessibility tree is relevant to the task, that is a INFORMATION MEMORY you want to reply with. Then look at the last action performed, if the two accessibility trees indicates that the action was successful. Only include concise and summarized information of successful actions that complete IMPORTANT SUBTASKS as a TASK MEMORY you want to reply with. "},
                        {"role": "system",
                         "content": "Give your final reply in the form '''info memory you reply with|important subtask summaries you reply with''', where | is used to delimit the information memory and task memory you want to reply with. If you don't want to store a field, just reply with that side empty. Remember to enclose your final reply with '''."}
                        ]
            old_tree_cleaned = self.process_axtree_memory(old_obs)
            new_tree_cleaned = self.process_axtree_memory(new_obs)
            messages.append({"role": "user",
                             f"content": f"Intended task: {intent}\nLast action performed: {last_action}\nOld accessibility tree: \n'''\n {old_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"})

            return messages
        return ''
    def construct_prompt(self, cur_obs: AxObservation, model_name) -> str:
        match self.phase:
            case Phase.CHOOSING_URL:
                return self.construct_url_prompt(self.intent, cur_obs, model_name)
            case Phase.CHOOSING_ELEMENTS:
                return self.construct_elements_prompt(self.intent, cur_obs, model_name)
            case _:
                raise Exception(f'Invalid phase prompt construct, HOW????? {self.phase}')

    def extract_interaction_info(self, xpath, html):  # TODO USE AXTREE ROLES
        if '<a' in html:
            return Action(Action.Type.CLICK, xpath, html)
        if (
                '<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "type=\"radio\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and (
                "<div" not in html):  # filter out div?
            return Action(Action.Type.CLICK, xpath, html)
        if (
                "<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html and "type=\"radio\"" not in html:
            return Action(Action.Type.INPUT, xpath, html)
        if "type=\"checkbox\"" in html:
            return Action(Action.Type.CLICK, xpath, html)
        if "<option" in html:  # TODO DOUBLE CHECK THIS CAN ACTUALLY BE CLICKED
            return Action(Action.Type.CLICK, xpath, html)

        return None

    def process_axtree_action(self, obs: AxObservation):
        counter = 1
        action_list = [Action(Action.Type.STOP, None, None)]
        cleaned_tree = "[0] STOP: STOP AND FINISH\n"


        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'])
                reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                if node_action:
                    action_list.append(node_action)
                    if ('radio' in obs.nodes_info[i]['html'] or 'checkbox' in obs.nodes_info[i]['html'] or '<input' in
                        obs.nodes_info[i]['html']) and len(reqs) > 0:
                        if node_action.action_type == Action.Type.INPUT:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {reqs}\n"
                        else:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
                    counter += 1
                else:
                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        print(cleaned_tree)
        return cleaned_tree, action_list

    def process_axtree_memory(self, obs: AxObservation):
        tree_cleaned = "[0] STOP: STOP AND FINISH\n"
        obs_counter = 1

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'])
                reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                if node_action:
                    if ('radio' in obs.nodes_info[i]['html'] or 'checkbox' in obs.nodes_info[i]['html'] or '<input' in
                        obs.nodes_info[i]['html']) and len(reqs) > 0:
                        if node_action.action_type == Action.Type.INPUT:
                            tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {reqs}\n"
                        else:
                            tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
                else:
                    tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"

        return tree_cleaned

    def get_next_action(self, cur_obs: AxObservation) -> Action:
        self.old_obs = cur_obs
        prompt_for_agent, answer_values = self.construct_prompt(cur_obs, model_name = 'gpt-4-0125-preview') # prompt_for_agent: str, answer_values: list[Actions]
        (final_index, final_string) = call_llm(prompt_for_agent, model_name = 'gpt-4-0125-preview')
        if final_index and final_index != -1:
            desired_action = answer_values[int(final_index)]
            if desired_action.action_type == Action.Type.INPUT:
                desired_action.set_input_string(final_string)
            self.last_action = desired_action
            return desired_action
        return Action(Action.Type.STOP, None, None) # TODO HANDLE FAILED GPT RETURNS BETTER


    def handle_memory(self, new_obs: AxObservation):
        memory_prompt_for_agent = self.construct_memory_prompt(self.intent, self.last_action, self.old_obs, new_obs, model_name = 'gpt-4-0125-preview')
        (info_mem, task_mem) = llm_manage_memory(memory_prompt_for_agent, model_name = 'gpt-4-0125-preview')
        print(info_mem)
        print("\n")
        print(task_mem)