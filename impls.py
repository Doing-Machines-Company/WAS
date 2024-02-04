from __future__ import annotations
import google.generativeai as genai
import time
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
import urllib.parse
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/cem/.config/gcloud/application_default_credentials.json"
class Phase(Enum):
    CHOOSING_URL = auto()
    CHOOSING_ELEMENTS = auto()
    # HANDLING_MEMORY = auto()

class BaseAgent(Agent):
    '''
    Assumptions:
    "required = \"true\"" means a required field for interactables
    Uses AxTreeObservation
    Anything that's not a button press does not need task_management summarization between two trees


    '''

    def __init__(self, intent: str):
        self.intent = intent
        # self.base_url = None
        # self.base_obs = None
        self.last_action_and_envtag = None
        self.old_obs = None
        self.phase = Phase.CHOOSING_ELEMENTS # or 'choosing_elements' (or 'handling_memory') # TODO MAKE ENUM TYPE


        self.current_subtask = ""

    def aggressive_normalize_url(self, url):  # Very aggressive normalization
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme if parsed_url.scheme else 'http'
        netloc = parsed_url.netloc
        path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
        # Ignoring the query and fragment
        normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
        return normalized_url

    def __construct_url_prompt(self, intent: str, new_obs: AxObservation, model_name: str) -> str:  # TODO, ignored for now
        pass



    def __construct_elements_prompt(self, cur_obs: AxObservation, model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT
        cleaned_tree, action_list = self.__process_axtree_action(cur_obs)
        if model_name.startswith('gpt'):
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a task, and an accessibility tree. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. "},
                {"role": "system",
                 "content": "The accessibility tree is reflective of the layout of the webpage. If an option has 'Important information', pay attention to all important information of that option. "},
                {"role": "system",
                 "content": "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. The input_string parameter is only used when the action you select is an action with INPUT FIELD in it's text. Do not choose options that are labelled 'Already selected'. "},
                {"role": "system",
                 "content": "First repeat list all of the actions with the 'Important information' label along with all of their information, using the action number in the square brackets. "},
                {"role": "system",
                 "content": "Then you must generate all subtasks needed to complete your task. Note that one of many actions from the tree may be sufficient for completing one subtask. "},
                {"role": "system",
                 "content": "Then using your 'Important information' action list, reason through your generated subtasks one-by-one to judge which subtasks are already completed by the actions that you listed out with important information. "},
                {"role": "system",
                 "content": "Then reason through your subtasks one-by-one to decide which subtasks are incomplete. You the first incomplete subtask is the optimal action. Then finally, please give me python code using the python choose_option function. "}]

            messages.append({"role": "user",
                             f"content": f"This is your task: {self.intent}\nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})

        if model_name.startswith('gemini'):
            messages = (
                 "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a task, and an accessibility tree. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. "
                 "The accessibility tree is reflective of the layout of the webpage. If an option has '|', pay attention to what's between those lines, it will tell you if an option has already been selected and if an option is required. Do not choose options that are already selected. "
                 "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. The input_string parameter is only used when the action you select is an action with INPUT FIELD in it's text. Pay attention to anything that is required."
                 "First look at the task, then look at the task completion progress, then you must generate subtasks using both pieces of information, reasong through these step-by-step. Reason through every single possible action labelled with a number in brackets at the start carefully, step-by-step, to decide which action you should perform first. Do your best to select an answer. If multiple steps are needed, select the first step as your option. Give me the code for choose_option.\n")

            messages += f"This is your task: {self.intent}\nTask completion progress: DNE FIX THIS!!!!!! \nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"

        return messages, action_list
        return ''

    def __construct_memory_prompt(self, intent: str, last_action: (Action, EnvironmentChange), base_obs: AxObservation, new_obs: AxObservation,
                                model_name: str) -> str:  # NOT NEEDED FOR MemGPT
        base_tree_cleaned = self.__process_axtree_memory(base_obs)
        new_tree_cleaned = self.__process_axtree_memory(new_obs)
            
        if model_name.startswith('gpt'):
            messages = [{"role": "system",
                         "content": "You are a very attentive robot who is responsible for judging if an action was successful, and why if it is unsuccessful why it failed. You exist on a web shop. "},
                        {"role": "system",
                         "content": "I'm giving you the python function store_information(judgement: str), where the string 'judgement' is the result of your reasoning. You must call the python function store_information in your reply. "},
                        {"role": "system",
                         "content": "I am going to give you two accessibility trees and an action. The accessibility trees represent the states of the website before the last action was performed. "},
                        {"role": "system",
                         "content": "First list list all the differences between the two trees. Then reason through the differences to judge whether the action succeeded or failed. Successful actions are explicitly clear. Reason through the differences to give reasons why the action may have failed. Then give me a summary of your reasoning. This summary is your 'judgement'. "},
                        {"role": "system",
                         "content": "You must call the python function store_information in your reply where the 'judgement' parameter for store_information is your summary. Finally, please give me the python code using the python store_information function I gave you."},
                        ]
            messages.append({"role": "user",
                             f"content": f"Intended task: {intent}\nLast action performed: {last_action.tree_line}\nOld accessibility tree:\n'''{base_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"})

            return messages
        if model_name.startswith('gemini'):
            messages =  ("You are a python function calling task evaluation robot for a shopping website. I am going to give you a task, the last action performed on a webshop, and two accessibility trees. The base tree is basic state of the page, and the new accessibility tree is the state of the website after the last action was performed. "
                         "A IMPORTANT SUBTASK is a subtask that is essential to the completion of a task. IMPORTANT SUBTASKS are subtasks that must be completed in order for your task to be completed. Tasks cannot be completed without completing all IMPORTANT SUBTASKS. Any subtasks that involve discovery or navigation are UNIMPORTANT. "
                         "FAILURE INFORMATION is information about the failure of the last action performed. If the difference between the two trees indicate that the last action's intended goal failed, you need to return FAILURE INFORMATION. FAILURE INFORMATION includes: \n1. The action that failed\n2. All the reasons why the action failed"
                         "SUCCESS INFORMATION is information about the success of the last action performed. If the difference between the two trees indicate that the last action's intended goal succeeded or already completed, you need to return SUCCESS INFORMATION. SUCCESS INFORMATION is a concise string that includes: \n1. The action that was successful\n2. A summary of the subtask that was successfully completed and how it's relevant to completing the TASK"
                         "You are given three python functions:\nstore_FAILURE_INFOMRATION(failure_info: str)\nstore_SUCCESS_INFORMATION(subtask_info: str)\nMOVE_ON()\nYou must reply with only one of these functions in your reply. "
                         "List the differences between the two accessibility trees. Then step-by-step reason about if an action was IMPORTANT. Then step-by-step reason about if an action was successful. If the action attempted to complete an IMPORTANT SUBTASK, give me the python code for calling either store_FAILURE_INFOMRATION to store either FAILURE INFORMATION if the action failed or store_SUCCESS_INFORMATION to store SUCCESS INFORMATION if the action succeeded. If the last action was UNIMPORTANT, give me the python function MOVE_ON(). Give me the python code for one of these functions.\n")
            messages +=  f"Intended task: {intent}\nLast action performed: {last_action.tree_line}\nBase accessibility tree: \n'''\n {base_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"


           
            return messages
        return ''
    def __construct_prompt(self, cur_obs: AxObservation, model_name) -> str:
        match self.phase:
            case Phase.CHOOSING_URL:
                return self.__construct_url_prompt(self.intent, cur_obs, model_name)
            case Phase.CHOOSING_ELEMENTS:
                return self.__construct_elements_prompt(cur_obs, model_name)
            case _:
                raise Exception(f'Invalid phase prompt construct, HOW????? {self.phase}')

    def __extract_interaction_info(self, xpath, html, role):


        important_clickables = [
            'button',
        ]

        select_clickables = [
            'checkbox', 'radio', 'menuitem',
            'tab', 'treeitem', 'switch', 'option', 'menuitemcheckbox',
            'menuitemradio', 'gridcell', 'columnheader', 'rowheader',
            'slider', 'listbox', 'tree',
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
            'combobox', 'textarea', 'spinbutton'
        ]

        if role.strip() == 'link':
            return Action(Action.Type.CLICK_LINK, xpath, html)

        elif role.strip() in important_clickables:
            return Action(Action.Type.CLICK_IMPORTANT, xpath, html)

        elif role.strip() in select_clickables:
            return Action(Action.Type.CLICK_SELECT, xpath, html)

        elif role.strip() in input_roles:
            return Action(Action.Type.INPUT, xpath, html)

        return None

    def process_node_properties(self, props_raw, html, env_tags=None):
        props = []
        if env_tags and env_tags in EnvironmentChange.change_log:
            match env_tags.action_type:
                case Action.Type.INPUT:
                    props.append(f"|Already input: {EnvironmentChange.change_log[env_tags]}|")
                case Action.Type.CLICK_LINK:
                    props.append("|Already visited|")
                case Action.Type.CLICK_IMPORTANT:
                    if EnvironmentChange.change_log[env_tags] != "":
                        props.append(f"|{EnvironmentChange.change_log[env_tags]}|")
                case Action.Type.CLICK_SELECT:
                    # Should be dealt with by checked.etc below
                    pass

        # selected_flag = False

        if "checked: true" in str(props_raw):
            props.append("This option already selected")
            # selected_flag = True

        if "required: True" in props_raw or "required=\"true\"" in html:
            props.append("Only one of each type required")








        if len(props) > 0:
            result = "| Important information: " + ". ".join(props)
            return result
        return ""


    def __process_axtree_action(self, obs: AxObservation):
        counter = 1
        action_list = [(Action(Action.Type.STOP, None, None), EnvironmentChange(obs.url, None, Action.Type.STOP))]
        cleaned_tree = "[0] CHOOSE THIS IF TASK FINISHED\n"

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'])
                # reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]


                if node_action:
                    env_tags = EnvironmentChange(obs.url, obs.nodes_info[i]['html'], node_action.action_type)
                    props = self.process_node_properties(obs.nodes_info[i]['properties'], obs.nodes_info[i]['html'], env_tags)


                    if node_action.action_type == Action.Type.INPUT:
                        tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}INPUT FIELD: {obs.nodes_info[i]['name']} {props}\n"
                    else:
                        tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {props}\n"

                    counter += 1
                    cleaned_tree += tree_add
                    node_action.set_tree_line(tree_add)
                    action_list.append((node_action, env_tags))
                else:
                    cleaned_tree += f"(Not an action){obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"(Not an action){obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        print(cleaned_tree)
        return cleaned_tree, action_list

    def __process_axtree_memory(self, obs: AxObservation):
        tree_cleaned = ""

        for i in range(len(obs.nodes_info)):
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'])
                # reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
                props = self.process_node_properties(obs.nodes_info[i]['properties'], obs.nodes_info[i]['html'])
                if node_action:
                    if node_action.action_type == Action.Type.INPUT:
                        tree_cleaned += f"{obs.nodes_info[i]['indent']}INPUT FIELD: {obs.nodes_info[i]['name']} {props}\n"
                    else:
                        tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {props}\n"
                else:
                    tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"

        return tree_cleaned

    def get_next_action(self, cur_obs: AxObservation) -> Action:
        # if self.base_url is None:
        #     self.base_url = self.aggressive_normalize_url(cur_obs.url)
        #     self.base_obs = cur_obs
        # elif self.aggressive_normalize_url(cur_obs.url) != self.base_url:
        #     self.base_url = cur_obs.url
        #     self.base_obs = cur_obs
        #     # TODO PURGE SOME MEMORY HERE
        #
        #
        self.old_obs = cur_obs
        prompt_for_agent, answer_values = self.__construct_prompt(cur_obs, model_name = 'gpt-3.5-turbo-0125') # prompt_for_agent: str, answer_values: list[Actions]
        (final_index, final_string) = self.__call_llm_action(prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
        if final_index and final_index != -1:
            desired_action = answer_values[int(final_index)][0]
            if desired_action.action_type == Action.Type.INPUT:
                desired_action.set_input_string(final_string)
            self.last_action_and_envtag = answer_values[int(final_index)]
            new_change = answer_values[int(final_index)][1]



            EnvironmentChange.change_log[new_change] = desired_action.input_string


            return desired_action
        return Action(Action.Type.STOP, None, None) # TODO HANDLE FAILED GPT RETURNS BETTER


    def handle_memory(self, new_obs: AxObservation):
        match self.last_action_and_envtag[0].action_type:
            case Action.Type.STOP:
                return
            case Action.Type.INPUT:
                return
            case Action.Type.CLICK_LINK:
                return
            case Action.Type.CLICK_IMPORTANT:
                memory_prompt_for_agent = self.__construct_memory_prompt(self.intent, self.last_action_and_envtag[0], self.old_obs, new_obs, model_name = 'gpt-3.5-turbo-0125')
                task_mem = self.__llm_manage_task_memory(memory_prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
                if task_mem != "":
                    EnvironmentChange.change_log[self.last_action_and_envtag[1]] = task_mem

    def __call_llm_action_filter(self, prompt, model_name='gpt-3.5-turbo-1106'):
        if model_name.startswith('gpt'):
            response = client.chat.completions.create(
                model=model_name,
                # model="gpt-3.5-turbo-1106",
                messages=prompt,
                temperature=0,
                max_tokens=2500,
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
                max_tokens=2500,
                # top_p=0,
                seed=12345678
            )

            result = response.choices[0].message.content
        elif model_name.startswith('gemini'):
            GOOGLE_API_KEY = 'AIzaSyBu8ecdjq4gzAGbT5Tk-bQm38S0WZikyDs'
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
            # Generate the response
            response = model.generate_content(prompt)

            # Introduce a delay of 1 second to limit to 60 requests per minute
            #time.sleep(1)

            # Return the text response
            #print(response.candidates)
            if len(response.candidates) > 0:
                response = response.candidates[0].content.parts[0].text.strip()
            else:
                response = response.text.strip()
            result = response
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
                max_tokens=2500,
                # top_p=0,
                seed=12345678
            )
            result = response.choices[0].message.content
            print(f"GPT RAW RETURN MEMORY: {result}")
            pattern1 = r"store_information\(\"(.*?)\"\)"
            pattern2 = r"store_information\(\'(.*?)\'\)"

            # Searching the LLM output for the pattern
            matches1 = re.findall(pattern1, result)
            matches2 = re.findall(pattern2, result)

            if len(matches1) > 0:
                for match in matches1:
                    return match.strip()
            elif len(matches2) > 0:
                for match in matches2:
                    return match.strip()

        if model_name.startswith('gemini'):
            GOOGLE_API_KEY = 'AIzaSyBu8ecdjq4gzAGbT5Tk-bQm38S0WZikyDs'
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
            # Generate the response
            response = model.generate_content(prompt)

            # Introduce a delay of 1 second to limit to 60 requests per minute
            #time.sleep(1)

            # Return the text response
            #print(response.candidates)
            if len(response.candidates) > 0:
                response = response.candidates[0].content.parts[0].text.strip()
            else:
                response = response.text.strip()
            result = response

        print(f"GPT RAW RETURN MEMORY: {result}")
        pattern1 = r"store_SUCCESS_INFORMATION\(\"(.*?)\"\)"
        pattern2 = r"store_SUCCESS_INFORMATION\(\'(.*?)\'\)"
        pattern3 = r"store_FAILURE_INFOMRATION\(\"(.*?)\"\)"
        pattern4 = r"store_FAILURE_INFOMRATION\(\'(.*?)\'\)"
        pattern5 = r"MOVE_ON\(\)"

        # Searching the LLM output for the pattern
        matches1 = re.findall(pattern1, result)
        matches2 = re.findall(pattern2, result)
        matches3 = re.findall(pattern3, result)
        matches4 = re.findall(pattern4, result)
        matches5 = re.findall(pattern5, result)

        if len(matches1) > 0:
            for match in matches1:
                return match.strip()
        elif len(matches2) > 0:
            for match in matches2:
                return match.strip()
        elif len(matches3) > 0:
            for match in matches3:
                return match.strip()
        elif len(matches4) > 0:
            for match in matches4:
                return match.strip()
        else:
            print("FAILED STORING MEMORY")
            return ""
