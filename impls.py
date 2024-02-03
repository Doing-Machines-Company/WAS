from __future__ import annotations
from models import *
from typing import Any, Optional, Union
from drivers import *
from typing import Optional
from action import Action
from enum import Enum, auto
from openai import OpenAI
import os
import re
import json
from typing import Optional
from environment_logger import EnvironmentChange
import copy

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

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
        self.environmental_changes = dict()
        self.current_subtask = ""

    def __construct_url_prompt(self, intent: str, new_obs: AxObservation, model_name: str) -> str:  # TODO, ignored for now
        pass

    def __construct_elements_filter(self, cur_obs: AxObservation, model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT
        if model_name.startswith('gpt'):
            cleaned_tree, action_list = self.__process_axtree_action(cur_obs)
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select options. I am going to give you a task, and an accessibility tree. Some lines are labelled with a number in square brackets, these lines are actions you can select. You must select actions from the accessibility tree that are labeled with a number in square brackets at the start of each row. "},
                {"role": "system",
                 "content": "You have the python function choose_options(selected_numbers: list[int]) which takes in a list of numbers. You must call the python function choose_options in your reply. selected_numbers is a list you must call the function with."},
                {"role": "system",
                 "content": "First look at the available action choices, and the tasks which have already been completed, then generate subtasks that need to be done using the available options as subtasks when they are relevant. If an action has PROPERTIES, it will tell you if an option is required or already selected. Select all actions that may help you complete the task, by giving me the code to the python function choose_options with the action numbers passed through as a list of integers selected_numbers."}]

            messages.append({"role": "user",
                             f"content": f"This is your task: {self.intent}\nCompleted subtasks: {self.task_memory}\nChoose your helpful actions from this accessibility tree: \n'''\n {cleaned_tree}\n'''"})

            return messages, action_list
        return ''

    def __construct_elements_prompt(self, cur_obs: AxObservation, wanted_indexes: list[int], model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT
        if model_name.startswith('gpt'):
            cleaned_tree = self.__process_axtree_action_pruned(cur_obs, wanted_indexes)
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a task, and an accessibility tree. Some lines are labelled with a number in square brackets, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. "},
                {"role": "system",
                 "content": "The accessibility tree is reflective of the layout of the webpage. If an option has PROPERTIES, it will tell you if an option has already been selected and if an option is required. "},
                {"role": "system",
                 "content": "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The input_string parameter is only used when the action you select is an action with INPUT FIELD in it's text. "},
                {"role": "system",
                 "content": "First look at the available action choices, and the tasks which have already been completed, then generate subtasks that need to be done using the available options as subtasks when they are relevant. Reason through every single possible action labelled with a number in brackets at the start carefully, step-by-step. Do your best to select an answer. If multiple steps are needed, select only the first step as your option. For example, if the final action you choose is action [102] with input \"something\", you will reply with choose_option(102, \"something\"). Give me the code for calling choose_option to select an option. "}]

            messages.append({"role": "user",
                             f"content": f"This is your task: {self.intent}\nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})

            return messages
        return ''

    def __construct_memory_prompt(self, intent: str, last_action: Action, old_obs: AxObservation, new_obs: AxObservation,
                                model_name: str) -> str:  # NOT NEEDED FOR MemGPT
        if model_name.startswith('gpt'):
            messages = [{"role": "system",
                         "content": f"You are a python function calling evaluation robot for an agent on a website. I am going to give you a task, the last action performed on a webshop, and two accessibility trees. The first accessibility tree is the previous state of the webpage, and the second accessibility tree is the current state of the webpage after the action was performed. "},
                        {"role": "system",
                         "content": "A IMPORTANT SUBTASK is a subtask that is essential to the completion of a task. For example if a task was adding a list of items to the cart, then adding an item on the list to cart would be an IMPORTANT SUBTASK, while clicking on a link to a different page would be an UNIMPORTANT SUBTASK, as clicking on a link is not essential to completing this example task. Any subtasks that involve discovery or navigation are UNIMPORTANT. "},
                        {"role": "system",
                         "content": "You are given the python function store_IMPORTANT_SUBTASK(subtask_info: str) which takes in a string. You must call the python function store_IMPORTANT_SUBTASK in your reply."},
                        {"role": "system",
                         "content": f"First look at the task, then you must generate subtasks that can help you complete this task, reasong through these step-by-step. Look at the last action performed, include concise and human-understandable information of successful actions that complete IMPORTANT SUBTASKS in the store_IMPORTANT_SUBTASK function parameter you call, include why the subtask was needed for the task to be completed. If the last_action failed, include the reason it failed. IMPORTANT SUBTASKS are subtasks that must be completed in order for your task to be completed. Give me the code for calling store_IMPORTANT_SUBTASK with relevant information."},

                        ]
            old_tree_cleaned = self.__process_axtree_memory(old_obs)
            new_tree_cleaned = self.__process_axtree_memory(new_obs)
            messages.append({"role": "user",
                             f"content": f"Intended task: {intent}\nLast action performed: {last_action}\nOld accessibility tree: \n'''\n {old_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"})

            return messages
        return ''
    def __construct_prompt(self, cur_obs: AxObservation, model_name) -> str:
        match self.phase:
            case Phase.CHOOSING_URL:
                return self.__construct_url_prompt(self.intent, cur_obs, model_name)
            case Phase.CHOOSING_ELEMENTS:
                filter_prompt, action_list = self.__construct_elements_filter(cur_obs, model_name)
                numbers = sorted(self.__call_llm_action_filter(filter_prompt))
                filtered_actions = []
                for i in numbers:
                    filtered_actions.append(action_list[i])





                return self.__construct_elements_prompt(cur_obs, numbers, model_name), filtered_actions
            case _:
                raise Exception(f'Invalid phase prompt construct, HOW????? {self.phase}')

    def __extract_interaction_info(self, xpath, html, role):


        clickables = [
            'button', 'menuitem', 'checkbox', 'radio',
            'tab', 'treeitem', 'switch', 'option', 'menuitemcheckbox',
            'menuitemradio', 'gridcell', 'columnheader', 'rowheader',
            'slider', 'spinbutton', 'listbox', 'tree',
            'grid', 'tabpanel', 'alert', 'alertdialog', 'dialog',
            'log', 'marquee', 'timer', 'tooltip', 'banner',
            'complementary', 'contentinfo', 'form', 'main', 'navigation',
            'region', 'search', 'status', 'img', 'note', 'application',
            'article', 'cell', 'definition', 'directory', 'document',
            'feed', 'figure', 'group', 'heading', 'img', 'list',
            'listitem', 'math', 'progressbar', 'row', 'rowgroup',
            'separator', 'toolbar', 'tooltip', 'presentation'
        ]

        input_roles = [
            'textbox', 'searchbox', 'slider', 'spinbutton', 'radiogroup',
            'checkbox', 'radio', 'switch', 'option', 'listbox',
            'combobox', 'textarea'
        ]
        if role.strip() == 'link':
            return Action(Action.Type.CLICK_LINK, xpath, html)
        elif role.strip() in clickables:
            return Action(Action.Type.CLICK_GENERAL, xpath, html)
        elif role.strip() in input_roles:
            return Action(Action.Type.INPUT, xpath, html)
        return None

    def __process_axtree_action(self, obs: AxObservation, include_changed = True):
        counter = 1
        action_list = [(Action(Action.Type.STOP, None, None), EnvironmentChange(obs.url, None, Action.Type.STOP))]
        cleaned_tree = "[0] STOP: STOP AND FINISH\n"

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'])
                # reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                props = obs.nodes_info[i]['properties']

                if node_action:
                    env_tags = EnvironmentChange(obs.url, obs.nodes_info[i]['html'], node_action.action_type)
                    action_list.append((node_action, env_tags))
                    if env_tags in EnvironmentChange.change_log:
                        properties_string_1 = f"PROPERTIES: {props}" if 'required: True' in str(props) else ""
                        properties_string_2 = f"PROPERTIES: {props}" if ('require' in str(props) or obs.nodes_info[i]['role'] in ['radio', 'checkbox']) else ""
                        if node_action.action_type == Action.Type.INPUT and 'required: True' in props:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}INPUT FIELD: {obs.nodes_info[i]['name']} {properties_string_1}. Already input: {EnvironmentChange.change_log[env_tags]} \n"
                        elif node_action.action_type == Action.Type.CLICK_LINK:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} Already visited\n"
                        elif node_action.action_type == Action.Type.CLICK_GENERAL:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {properties_string_2}\n"
                        else:
                            print(node_action.action_type)
                            Exception("UNKNOWN ACTION TYPE")
                    else:
                        properties_string_1 = f"PROPERTIES: {props}" if 'required: True' in str(props) else ""
                        properties_string_2 = f"PROPERTIES: {props}" if ('required: True' in str(props) or obs.nodes_info[i]['role'] in ['radio', 'checkbox']) else ""
                        if node_action.action_type == Action.Type.INPUT:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {properties_string_1}\n"
                        else:
                            cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {properties_string_2}\n"
                    counter += 1
                else:
                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        print(cleaned_tree)
        return cleaned_tree, action_list

    def __process_axtree_action_pruned(self, obs: AxObservation, wanted_indexes, include_changed = True):
        counter = 1
        true_counter = 1 if 0 in wanted_indexes else 0
        # print("TRUE COUNTER")
        # print(true_counter)
        # input("LOOK TRUE COUNT")
        cleaned_tree = "[0] STOP: STOP AND FINISH\n" if 0 in wanted_indexes else ""

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'])
                # reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                props = obs.nodes_info[i]['properties']

                if node_action:
                    env_tags = EnvironmentChange(obs.url, obs.nodes_info[i]['html'], node_action.action_type)
                    if env_tags in EnvironmentChange.change_log:
                        true_counter_string = f"[{true_counter}]" if counter in wanted_indexes else ""
                        properties_string_1 = f"PROPERTIES: {props}" if 'required: True' in str(props) else ""
                        properties_string_2 = f"PROPERTIES: {props}" if ('require' in str(props) or obs.nodes_info[i]['role'] in ['radio', 'checkbox']) else ""
                        if node_action.action_type == Action.Type.INPUT and 'required: True' in props:
                            cleaned_tree += f"{true_counter_string}{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {properties_string_1}. Already input: {EnvironmentChange.change_log[env_tags]} \n"
                        elif node_action.action_type == Action.Type.CLICK_LINK:
                            cleaned_tree += f"{true_counter_string}{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} Already visited\n"
                        elif node_action.action_type == Action.Type.CLICK_GENERAL:
                            cleaned_tree += f"{true_counter_string}{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {properties_string_2}\n"
                        else:
                            print(node_action.action_type)
                            Exception("UNKNOWN ACTION TYPE")
                    else:
                        properties_string_1 = f"PROPERTIES: {props}" if 'required: True' in str(props) else ""
                        properties_string_2 = f"PROPERTIES: {props}" if ('required: True' in str(props) or obs.nodes_info[i]['role'] in ['radio', 'checkbox']) else ""
                        if node_action.action_type == Action.Type.INPUT:
                            cleaned_tree += f"{f"[{true_counter}]" if counter in wanted_indexes else ""}{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {properties_string_1}\n"
                        else:
                            cleaned_tree += f"{f"[{true_counter}]" if counter in wanted_indexes else ""}{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {properties_string_2}\n"
                    if counter in wanted_indexes:
                        true_counter += 1
                    counter += 1
                else:
                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        print(cleaned_tree)
        return cleaned_tree

    def __process_axtree_memory(self, obs: AxObservation):
        tree_cleaned = "[0] STOP: STOP AND FINISH\n"

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'])
                # reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                reqs = obs.nodes_info[i]['properties']
                if node_action:
                    if node_action.action_type == Action.Type.INPUT:
                        tree_cleaned += f"{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {reqs}\n"
                else:
                    tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"

        return tree_cleaned

    def get_next_action(self, cur_obs: AxObservation) -> Action:
        self.old_obs = cur_obs
        prompt_for_agent, answer_values = self.__construct_prompt(cur_obs, model_name = 'gpt-3.5-turbo-0125') # prompt_for_agent: str, answer_values: list[Actions]
        (final_index, final_string) = self.__call_llm_action(prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
        if final_index and final_index != -1:
            desired_action = answer_values[int(final_index)][0]
            if desired_action.action_type == Action.Type.INPUT:
                desired_action.set_input_string(final_string)
            self.last_action = desired_action
            input("LOOK AT DESIRED")
            new_change = answer_values[int(final_index)][1]



            EnvironmentChange.change_log[new_change] = desired_action.input_string


            return desired_action
        return Action(Action.Type.STOP, None, None) # TODO HANDLE FAILED GPT RETURNS BETTER


    def handle_memory(self, new_obs: AxObservation):
        memory_prompt_for_agent = self.__construct_memory_prompt(self.intent, self.last_action, self.old_obs, new_obs, model_name = 'gpt-3.5-turbo-0125')
        task_mem = self.__llm_manage_task_memory(memory_prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
        if task_mem != "":
            print("TASK MEM STORED")
            print(task_mem)
            self.task_memory.append(task_mem)
            print(self.task_memory)

    def __call_llm_action_filter(self, prompt, model_name='gpt-3.5-turbo-1106'):
        if model_name.startswith('gpt'):
            response = client.chat.completions.create(
                model=model_name,
                # model="gpt-3.5-turbo-1106",
                messages=prompt,
                temperature=0,
                max_tokens=1500,
                # top_p=0,
                seed=12345678
            )

            result = response.choices[0].message.content
            print(f"RAW FILTER CALL: {result}")

            pattern = r"choose_options\(\[([0-9, ]+)\]\)"

            # Searching the LLM output for the pattern
            match = re.search(pattern, result)

            # Initialize an empty list to store integers
            task_numbers = []

            if match:
                numbers_str = match.group(1)
                task_numbers = [int(num.strip()) for num in numbers_str.split(',')]
                return task_numbers
            else:
                return list()
            print("FAILED CALLING ACTION")

    def __call_llm_action(self, prompt, model_name='gpt-3.5-turbo-1106'):
        if model_name.startswith('gpt'):
            response = client.chat.completions.create(
                model=model_name,
                # model="gpt-3.5-turbo-1106",
                messages=prompt,
                temperature=0,
                max_tokens=1500,
                # top_p=0,
                seed=12345678
            )

            result = response.choices[0].message.content
            print(f"NEXT ACTION RAW: {result}")

            pattern = r'choose_option\((\d+),?\s*(?:\'([^\']*)\'|"([^"]*)"|None)?\)'

            # Searching the LLM output for the pattern
            matches = re.findall(pattern, result)

            # Printing the matches
            for match in matches:
                task_number, input_string_single, input_string_double = match[:3]
                input_string = input_string_single or input_string_double or ""
                return task_number, input_string
            print("FAILED CALLING ACTION")

    def __llm_manage_task_memory(self, prompt, model_name='gpt-3.5-turbo-1106'):
        if model_name.startswith('gpt'):
            response = client.chat.completions.create(
                model=model_name,
                # model="gpt-3.5-turbo-1106",
                messages=prompt,
                temperature=0,
                max_tokens=1500,
                # top_p=0,
                seed=12345678
            )

            result = response.choices[0].message.content
            print(f"GPT RAW RETURN MEMORY: {result}")
            pattern1 = r"store_IMPORTANT_SUBTASK\(\"(.*?)\"\)"
            pattern2 = r"store_IMPORTANT_SUBTASK\(\'(.*?)\'\)"

            # Searching the LLM output for the pattern
            matches1 = re.findall(pattern1, result)
            matches2 = re.findall(pattern2, result)

            if len(matches1) > 0:
                for match in matches1:
                    return match.strip()
            elif len(matches2) > 0:
                for match in matches2:
                    return match.strip()
            else:
                print("FAILED STORING MEMORY")
                return ""
