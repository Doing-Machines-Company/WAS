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
from bs4 import BeautifulSoup
from environment_logger import EnvironmentChange
import copy
import urllib.parse
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/cem/.config/gcloud/application_default_credentials.json"

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
        self.task_memory = []
        self.current_subtask = None

        with open('auxillary_jsons/external_links.json', 'r') as file:
            self.all_links = json.load(file)

    def aggressive_normalize_url(self, url: str):  # Very aggressive normalization
        '''
        Normalization which removes everything that's trailing (e.g., #p=1)
        
        :param url: 
        :return: 
        '''
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme if parsed_url.scheme else 'http'
        netloc = parsed_url.netloc
        path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
        # Ignoring the query and fragment
        normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
        return normalized_url

    def __construct_url_prompt(self, intent: str, new_obs: AxObservation, model_name: str) -> str:  # TODO Implement
        '''
        Not implemented
        
        :param intent: 
        :param new_obs: 
        :param model_name: 
        :return: 
        '''
        if model_name.startswith('gpt'):
            messages = {}
        return messages



    def __construct_elements_prompt(self, cur_obs: AxObservation, model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT, NEED MORE CODE GEN STABILITY
        '''
        Constructs the prompt for the model to generate a response for get_next_action, phases may be deprecated later
        
        :param cur_obs: 
        :param model_name: 
        :return: 
        '''
        cleaned_tree, action_list = self.__process_axtree_action(cur_obs)
        if model_name.startswith('gpt'):
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a main task, and an accessibility tree. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. The main task is your overall objective. "},
                {"role": "system",
                 "content": "The accessibility tree is reflective of the layout of the webpage. The indents are reflective of the structure of the page and the actions on it. "},
                {"role": "system",
                 "content": "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. The input_string parameter is only used when the action you select is an action with INPUT FIELD in it's text. If any of the information on this web page indicates that the task cannot be completed, move on to your next task or stop if you are finished. Pay attention to all information enclosed in in parentheses. Information in parentheses will tell you if an action has already been completed. Using the information in parentheses, list out all the actions and tasks that have already been completed. "},
                {"role": "system",
                 "content": "An IMPORTANT SUBTASK is a subtask that is essential to the completion of a task. IMPORTANT SUBTASKS are subtasks that must be completed in order for your task to be completed. IMPORTANT SUBTASKs can be completed by a single action on the page. Tasks cannot be completed without completing all IMPORTANT SUBTASKS. Any subtasks that involve discovery or navigation are UNIMPORTANT. "},
                {"role": "system",
                 "content": "Tell me what page you are currently on, and what can be done on the page that is relevant to your task. First reason step-by-step if your task can be completed without leaving this web page. Then you must generate general IMPORTANT SUBTASKs that are incomplete. "},
                {"role": "system",
                 "content": "Then reason step-by-step through all information in the tree that is enclosed in parentheses, and determine if that information indicates that your task is impossible. If this is your final task and it's impossible, choose the stop command. If this is not your final task, move on to your next task. "},
                {"role": "system",
                 "content": "Then you must reasonstep-by-step through all of your IMPORTANT SUBTASKs to determine the first incomplete IMPORTANT SUBTASK. The optimal action is the first action that completes a subtask that is still incomplete. Then finally, please give me python code using the python choose_option function. "}]

            messages.append({"role": "user",
                             f"content": f"This is your main task: {self.intent}\nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"})

        if model_name.startswith('gemini'):
            messages = (
                 "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a task, and an accessibility tree. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. "
                 "The accessibility tree is reflective of the layout of the webpage. If an option has '|', pay attention to what's between those lines, it will tell you if an option has already been selected and if an option is required. Do not choose options that are already selected. "
                 "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. The input_string parameter is only used when the action you select is an action with INPUT FIELD in it's text. Pay attention to anything that is required."
                 "First look at the task, then look at the task completion progress, then you must generate subtasks using both pieces of information, reasong through these step-by-step. Reason through every single possible action labelled with a number in brackets at the start carefully, step-by-step, to decide which action you should perform first. Do your best to select an answer. If multiple steps are needed, select the first step as your option. Give me the code for choose_option.\n")

            messages += f"This is your task: {self.intent}\nTask completion progress: DNE FIX THIS!!!!!! \nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"

        return messages, action_list
        return ''

    def __construct_completion_evaluation_prompt(self, last_action: (Action, EnvironmentChange), new_obs: AxObservation,
                                model_name: str) -> str:  
        '''
        Constructs prompt for task evaluation
        
        :param intent: 
        :param last_action: 
        :param base_obs: 
        :param new_obs: 
        :param model_name: 
        :return: 
        '''
        base_obs = self.old_obs
        last_action = self.last_action_and_envtag[0]
        
        base_tree_cleaned = self.__process_axtree_memory(base_obs)
        new_tree_cleaned = self.__process_axtree_memory(new_obs)


        print("BASE TREE")
        print(base_tree_cleaned)
        print("NEW TREE")
        print(new_tree_cleaned)
        input("LOOK AT TREES")

        if model_name.startswith('gpt'): # task no longer passed in
            messages = [{"role": "system",
                         "content": "You are a very attentive agent who is responsible for judging if an action was successful, and why if it is unsuccessful why it failed. You operate on a web shop. "},
                        {"role": "system",
                         "content": "You have the python function store_information(judgement: str), where the string 'judgement' is a summary of your reasoning. "},
                        {"role": "system",
                         "content": "I am going to give you two accessibility trees and the last action. The two accessibility trees are the state of the website before and after the last action. Pay attention to all options with 'alert' and all changes with lines labelled 'StaticText'. Pay attention to all information in parantheses in the accessibility tree before the action, these will tell you what options where selected/interacted with before the last action was performed. "},
                        {"role": "system",
                         "content": "First look at your last action, and tell me why it was taken. Then you must list all the differences between the two trees. Then reason through the differences to judge whether the action succeeded or failed. Any action that starts an intended process is a fully succesful action. Then give me a summary of your reasoning. "},
                        {"role": "system",
                         "content": "If the action succeded, your 'judgement' is about the success of the intent of the action. If the action failed, your 'judgement' is the reasons why the action failed. 'judgement' must be concise. You must call the python function store_information in your reply where the 'judgement' parameter for store_information is your summary. Finally, give me the python code using the python store_information function I gave you. "},
                        ]
            messages.append({"role": "user",
                             f"content": f"Main task: {self.intent}\nLast action performed: {last_action.tree_line}\nAccessibility tree before last action:\n'''{base_tree_cleaned}\n'''\nAccessibility tree after last action: \n'''\n {new_tree_cleaned}\n'''"})

            return messages
        if model_name.startswith('gemini'):
            messages =  ("You are a python function calling task evaluation robot for a shopping website. I am going to give you a task, the last action performed on a webshop, and two accessibility trees. The base tree is basic state of the page, and the new accessibility tree is the state of the website after the last action was performed. "
                         "A IMPORTANT SUBTASK is a subtask that is essential to the completion of a task. IMPORTANT SUBTASKS are subtasks that must be completed in order for your task to be completed. Tasks cannot be completed without completing all IMPORTANT SUBTASKS. Any subtasks that involve discovery or navigation are UNIMPORTANT. "
                         "FAILURE INFORMATION is information about the failure of the last action performed. If the difference between the two trees indicate that the last action's intended goal failed, you need to return FAILURE INFORMATION. FAILURE INFORMATION includes: \n1. The action that failed\n2. All the reasons why the action failed"
                         "SUCCESS INFORMATION is information about the success of the last action performed. If the difference between the two trees indicate that the last action's intended goal succeeded or already completed, you need to return SUCCESS INFORMATION. SUCCESS INFORMATION is a concise string that includes: \n1. The action that was successful\n2. A summary of the subtask that was successfully completed and how it's relevant to completing the TASK"
                         "You are given three python functions:\nstore_FAILURE_INFOMRATION(failure_info: str)\nstore_SUCCESS_INFORMATION(subtask_info: str)\nMOVE_ON()\nYou must reply with only one of these functions in your reply. "
                         "List the differences between the two accessibility trees. Then step-by-step reason about if an action was IMPORTANT. Then step-by-step reason about if an action was successful. If the action attempted to complete an IMPORTANT SUBTASK, give me the python code for calling either store_FAILURE_INFOMRATION to store either FAILURE INFORMATION if the action failed or store_SUCCESS_INFORMATION to store SUCCESS INFORMATION if the action succeeded. If the last action was UNIMPORTANT, give me the python function MOVE_ON(). Give me the python code for one of these functions.\n")
            messages +=  f"Intended task: {self.intent}\nLast action performed: {last_action.tree_line}\nBase accessibility tree: \n'''\n {base_tree_cleaned}\n'''\nNew accessibility tree: \n'''\n {new_tree_cleaned}\n'''"


           
            return messages
        return ''


    def __extract_interaction_info(self, xpath, html, role, obs_url):
        '''
        For a given element's information, create an action object

        :param xpath:
        :param html:
        :param role:
        :param obs_url:
        :return:
        '''
        important_clickables = [
            'button',
        ]

        select_clickables = [
            'checkbox', 'radio',
        ]

        general_clickables = [
            'menuitem',
             'treeitem', 'switch', 'option', 'menuitemcheckbox',
            'menuitemradio',
            'slider', 'listbox', 'tree',
            'grid',  'alert', 'alertdialog', 'dialog',
            'log', 'marquee', 'timer', 'tooltip', 'banner',
            'complementary', 'contentinfo', 'form', 'main', 'navigation',
            'region', 'search', 'status', 'img', 'note', 'application',
            'article', 'cell', 'definition', 'directory', 'document',
            'feed', 'figure', 'group', 'heading', 'img', 'list',
            'listitem', 'math', 'progressbar',
            'separator', 'toolbar', 'tooltip', 'presentation']

        input_roles = [
            'textbox', 'searchbox', 'slider', 'spinbutton', 'radiogroup',
            'checkbox', 'radio', 'switch', 'option', 'listbox',
            'combobox', 'textarea', 'spinbutton'
        ]

        currently_ignored = ['gridcell', 'columnheader', 'rowheader', 'tab',
            'tabpanel', 'row', 'rowgroup']

        if xpath.strip() != "" and html.strip() != "":
            if role.strip() == 'link':
                return Action(Action.Type.CLICK_LINK, xpath, html)

            elif role.strip() in important_clickables:
                return Action(Action.Type.CLICK_IMPORTANT, xpath, html)

            elif role.strip() == 'radio':
                return Action(Action.Type.CLICK_RADIO, xpath, html)

            elif role.strip() == 'checkbox':
                return Action(Action.Type.CLICK_CHECKBOX, xpath, html)

            elif role.strip() in general_clickables:
                return Action(Action.Type.CLICK_GENERAL, xpath, html)

            elif role.strip() in input_roles:
                return Action(Action.Type.INPUT, xpath, html)

        return None

    def process_node_properties(self, props_raw: list[str], html: str, env_tags: EnvironmentChange=None): # DOES NOT DO ANYTHING WITH RADIO
        '''
        Better formats one action for the prompt

        :param props_raw:
        :param html:
        :param env_tags:
        :return:
        '''
        props = []
        role_name = ""
        if env_tags:
            match env_tags.action_type:
                case Action.Type.INPUT:
                    role_name = "Input field: "
                    if env_tags and env_tags in EnvironmentChange.change_log:
                        props.append(f"Already input: {EnvironmentChange.change_log[env_tags]}")

                    if "required: True" in props_raw or "required=\"true\"" in html:
                        props.append("Required to input")

                case Action.Type.CLICK_LINK:
                    role_name = "Click link: "
                    if env_tags and env_tags in EnvironmentChange.change_log:
                        props.append("Already visited")

                case Action.Type.CLICK_IMPORTANT:
                    role_name = "Click: "
                    if env_tags and env_tags in EnvironmentChange.change_log and EnvironmentChange.change_log[env_tags] != "":
                        props.append(f"{EnvironmentChange.change_log[env_tags]}")

                case Action.Type.CLICK_CHECKBOX:

                    soup = BeautifulSoup(html, 'html.parser')
                    input_element = soup.find('input')
                    name_field = input_element.get('name', '')


                    role_name = "Choose to select: "
                    # if "checked: true" not in str(props_raw):
                    #     props.append("Unselected")

                    if "checked: true" in str(props_raw):
                        props.append("Already selected")
                    #
                    elif name_field != "":
                        props.append("Unselected")

                        if ("required: True" in props_raw or "required=\"true\"" in html) and name_field == "": # TODO This casing structure may cauase logical issues later on
                            props.append("Required")

                    # TODO MAKE ABOVE MORE EFFICEINT, THIS IS KIND OF REDUNDENT


                case Action.Type.CLICK_GENERAL:
                    role_name = ""
                    if "checked: true" in str(props_raw):
                        props.append("Already selected")
                    # if "required: True" in props_raw or "required=\"true\"" in html:
                    #     props.append("Required")

                case Action.Type.CLICK_RADIO:
                    print("RADIO NOT PROCESSED BY THIS FUNCTION")

        if len(props) > 0:
            result = " (" + ". ".join(props) + ")"
            return result, role_name
        return "", role_name

    def __skip_option(self, node_info: dict):
        '''
        Skips non-action options we don't care about
        Heuristic

        :param node_info:
        :return:
        '''
        ignored_roles = ["ListMarker", "Image"]
        if node_info['role'] in ignored_roles:
            return True
        return False

    def __skip_action(self, node_info: dict, node_action: Action, obs_url: str):
        '''
        Skips action options we don't care about
        Heuristic

        In general, skips links that we visit by just going to the url, to decrease noise

        :param node_info:
        :return:
        '''
        match node_action.action_type:
            case Action.Type.CLICK_LINK:
                href_regex = r'href="([^"]*)"'
                href_values = re.findall(href_regex, node_info['html'])
                if len(href_values) > 0:
                    for href_value in href_values:
                        if href_value.startswith('#') and href_value != '#':
                            return True
                        if self.aggressive_normalize_url(href_value) in self.all_links and self.aggressive_normalize_url(href_value) != self.aggressive_normalize_url(obs_url):
                            return True
            case Action.Type.CLICK_GENERAL:
                href_regex = r'href="([^"]*)"'
                href_values = re.findall(href_regex, node_info['html'])
                if len(href_values) > 0:
                    for href_value in href_values:
                        if href_value.startswith('#') and href_value != '#':
                            return True
                        if self.aggressive_normalize_url(
                                href_value) in self.all_links and self.aggressive_normalize_url(
                                href_value) != self.aggressive_normalize_url(obs_url):
                            return True
            case Action.Type.CLICK_IMPORTANT:
                if "<img src" in node_info['html']:
                    return True
        return False

    def __process_radios(self, radio_nodes: list[(dict, int, (Action, EnvironmentChange))]):
        '''
        Menu-ify a list of radio nodes
        radio_nodes are (obs.nodes_info[i], counter, (node_action, env_tags))
        :param radio_nodes:
        :return:
        '''
        properties_stacked = str([radio_nodes[i][0]['properties'] for i in range(len(radio_nodes))])
        html_stacked = str([radio_nodes[i][0]['html'] for i in range(len(radio_nodes))])
        checked_flag = "checked: true" in properties_stacked
        required_flag = "required: True" in properties_stacked or "required=\"true\"" in html_stacked
        tree_insert = ""
        # name_field = ""
        action_list = []

        for i in range(len(radio_nodes)):
            node_info = radio_nodes[i][0]
            counter = radio_nodes[i][1]
            node_action = radio_nodes[i][2][0]
            env_tags = radio_nodes[i][2][1]


            soup = BeautifulSoup(node_info['html'], 'html.parser')
            input_element = soup.find('input')
            # name_field = input_element.get('name', '').strip()

            if "checked: true" in node_info['properties']:
                node_action.set_tree_line(f"[{counter}]{node_info['indent']}       Select: {node_info['name']} (this option selected)")
                tree_insert +=  f"[{counter}]{node_info['indent']}       Select: {node_info['name']} (this option selected)\n"
                action_list.append((node_action, env_tags))
            elif checked_flag:
                node_action.set_tree_line(f"[{counter}]{node_info['indent']}       Select: {node_info['name']}")
                tree_insert +=  f"[{counter}]{node_info['indent']}       Select: {node_info['name']}\n"
                action_list.append((node_action, env_tags))
            else:
                node_action.set_tree_line(f"[{counter}]{node_info['indent']}       Select: {node_info['name']}")
                tree_insert += f"[{counter}]{node_info['indent']}       Select: {node_info['name']}\n"
                action_list.append((node_action, env_tags))

        if len(radio_nodes) > 0:
            if checked_flag:
                tree_insert = f"{radio_nodes[0][0]['indent']}Select option (selection already completed): \n" + tree_insert
            elif required_flag:
                tree_insert = f"{radio_nodes[0][0]['indent']}Select option (need doing, required to select): \n" + tree_insert
            else:
                tree_insert = f"{radio_nodes[0][0]['indent']}Select option: \n" + tree_insert
            tree_insert += '\n'

        return tree_insert, action_list

    def __process_axtree_action(self, obs: AxObservation):
        '''
        Heavily processes the tree for the prompt
        Skips options via function calls

        :param obs:
        :return:
        '''
        counter = 1
        action_list = [(Action(Action.Type.STOP, None, None), EnvironmentChange(obs.url, None, Action.Type.STOP))]
        cleaned_tree = "[0] Stop command (choose this if the task is finished or impossible)\n"


        scanning_radios = False
        current_radio_nodes = []
        tabled_options = set()

        for i in range(len(obs.nodes_info)):
            if self.__skip_option(obs.nodes_info[i]):
                continue
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'], obs.url)

                if node_action:
                    tree_add = None
                    if self.__skip_action(obs.nodes_info[i], node_action, obs.url):
                        continue

                    env_tags = EnvironmentChange(obs.url, obs.nodes_info[i]['html'], node_action.action_type)

                    props, role_name = self.process_node_properties(obs.nodes_info[i]['properties'], obs.nodes_info[i]['html'], env_tags)
                    if role_name == "":
                        role_name = obs.nodes_info[i]['role'] + ": "

                    if node_action.action_type == Action.Type.INPUT:
                        if scanning_radios:
                            scanning_radios = False
                            if len(current_radio_nodes) > 0:
                                tree_strings, radio_actions = self.__process_radios(current_radio_nodes)
                                cleaned_tree += tree_strings
                                action_list.extend(radio_actions)
                                current_radio_nodes = []
                        tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

                    elif node_action.action_type == Action.Type.CLICK_RADIO:
                        scanning_radios = True

                        soup = BeautifulSoup(obs.nodes_info[i]['html'], 'html.parser')
                        input_element = soup.find('input')
                        name_field = input_element.get('name', '').strip()

                        if name_field != '':
                            if name_field in tabled_options:
                                current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                            else:
                                if len(current_radio_nodes) > 0:
                                    tree_strings, radio_actions = self.__process_radios(current_radio_nodes)
                                    cleaned_tree += tree_strings
                                    action_list.extend(radio_actions)
                                    current_radio_nodes = []
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                                else:
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                        else:
                            tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"


                    else:
                        if scanning_radios:
                            scanning_radios = False
                            if len(current_radio_nodes) > 0:
                                tree_strings, radio_actions = self.__process_radios(current_radio_nodes)
                                cleaned_tree += tree_strings
                                action_list.extend(radio_actions)
                                current_radio_nodes = []
                        tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

                    counter += 1
                    if tree_add:
                        cleaned_tree += tree_add
                        node_action.set_tree_line(tree_add)
                        action_list.append((node_action, env_tags))
                else:
                    if scanning_radios:
                        scanning_radios = False
                        if len(current_radio_nodes) > 0:
                            tree_strings, radio_actions = self.__process_radios(current_radio_nodes)
                            cleaned_tree += tree_strings
                            action_list.extend(radio_actions)
                            current_radio_nodes = []

                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}You are currently on the page for: {obs.nodes_info[i]['name']}\n"

        if scanning_radios:
            scanning_radios = False
            if len(current_radio_nodes) > 0:
                tree_strings, radio_actions = self.__process_radios(current_radio_nodes)
                cleaned_tree += tree_strings
                action_list.extend(radio_actions)
                current_radio_nodes = []
        print(cleaned_tree)
        return cleaned_tree, action_list

    def __process_axtree_memory(self, obs: AxObservation):
        '''
        Almost identical to __process_axtree_action, but does not return action list

        :param obs:
        :return:
        '''
        counter = 1
        cleaned_tree = "[0] CHOOSE THIS IF TASK FINISHED OR IMPOSSIBLE\n"

        scanning_radios = False
        current_radio_nodes = []
        tabled_options = set()

        for i in range(len(obs.nodes_info)):
            if self.__skip_option(obs.nodes_info[i]):
                continue
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'],
                                                              obs.nodes_info[i]['role'], obs.url)

                if node_action:
                    tree_add = None
                    if self.__skip_action(obs.nodes_info[i], node_action, obs.url):
                        continue

                    env_tags = EnvironmentChange(obs.url, obs.nodes_info[i]['html'], node_action.action_type)

                    props, role_name = self.process_node_properties(obs.nodes_info[i]['properties'],
                                                                    obs.nodes_info[i]['html'], env_tags)
                    if role_name == "":
                        role_name = obs.nodes_info[i]['role'] + ": "

                    if node_action.action_type == Action.Type.INPUT:
                        if scanning_radios:
                            scanning_radios = False
                            if len(current_radio_nodes) > 0:
                                tree_strings, _ = self.__process_radios(current_radio_nodes)
                                cleaned_tree += tree_strings
                                current_radio_nodes = []
                        tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

                    elif node_action.action_type == Action.Type.CLICK_RADIO:
                        scanning_radios = True

                        soup = BeautifulSoup(obs.nodes_info[i]['html'], 'html.parser')
                        input_element = soup.find('input')
                        name_field = input_element.get('name', '').strip()

                        if name_field != '':
                            if name_field in tabled_options:
                                current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                            else:
                                if len(current_radio_nodes) > 0:
                                    tree_strings, _ = self.__process_radios(current_radio_nodes)
                                    cleaned_tree += tree_strings
                                    current_radio_nodes = []
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                                else:
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                        else:
                            tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"


                    else:
                        if scanning_radios:
                            scanning_radios = False
                            if len(current_radio_nodes) > 0:
                                tree_strings, _ = self.__process_radios(current_radio_nodes)
                                cleaned_tree += tree_strings
                                current_radio_nodes = []
                        cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
                        # tree_add = f"[{counter}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

                    counter += 1
                    if tree_add:
                        cleaned_tree += tree_add
                        node_action.set_tree_line(tree_add)
                else:
                    if scanning_radios:
                        scanning_radios = False
                        if len(current_radio_nodes) > 0:
                            tree_strings, _ = self.__process_radios(current_radio_nodes)
                            cleaned_tree += tree_strings
                            current_radio_nodes = []

                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}You are currently on the page for: {obs.nodes_info[i]['name']}\n"

        if scanning_radios:
            scanning_radios = False
            if len(current_radio_nodes) > 0:
                tree_strings, _ = self.__process_radios(current_radio_nodes)
                cleaned_tree += tree_strings
                current_radio_nodes = []
        return cleaned_tree

    def get_next_action(self, cur_obs: AxObservation) -> Action:
        '''
        Gets the next action to perform
        
        :param cur_obs: 
        :return: 
        '''
        self.old_obs = cur_obs
        prompt_for_agent, answer_values = self.__construct_elements_prompt(cur_obs, model_name = 'gpt-3.5-turbo-0125') # prompt_for_agent: str, answer_values: list[Actions]
        (final_index, final_string) = self.__call_llm_action(prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
        if final_index and final_index != -1:
            desired_action = answer_values[int(final_index)][0]
            # TODO IF DESIRED ACTION IS GOTO URL, THEN NO ENVIRONMENT CHANGE NEEDED. NEED TO FIND LINK TO GO TO.
            if desired_action.action_type == Action.Type.INPUT:
                desired_action.set_input_string(final_string)
            self.last_action_and_envtag = answer_values[int(final_index)]
            new_change = answer_values[int(final_index)][1]



            EnvironmentChange.change_log[new_change] = desired_action.input_string

            
            return desired_action
        return Action(Action.Type.STOP, None, None) # TODO HANDLE FAILED GPT RETURNS BETTER

    
    def __llm_long_range_task_memory_prompt(self, new_obs: AxObservation, model_name: str) -> str:
        messages = [{
                "role": "system",
                "content": "You are a management specialist for a shopping website. You act as support for an agent. "
            },
            {
                "role": "system",
                "content": "An IMPORTANT SUBTASK is a subtask that is essential to the completion of a goal. IMPORTANT SUBTASKS are subtasks that must be completed in order for the main goal to be completed. Tasks cannot be completed without completing all IMPORTANT SUBTASKS. Any subtasks that involve discovery or navigation are UNIMPORTANT. IMPORTANT SUBTASKS ignore specific website actions like clicks or option choices. "
            },
            {
                "role": "system",
                "content": "I am going to give you the main goal the agent is working on, a TASK MEMORY of IMPORTANT SUBTASKs that need to be completed, and the current accessibility tree which represents the state of the website. "
            },
            {
                "role": "system",
                "content": "First "
            }

        ]

    def __call_llm_task_memory(self, prompt, model_name: str) -> (str, str):
        pass

    def handle_memory(self, new_obs: AxObservation):
        '''
        Handles memory
        First judges task completion if the last action was a button (CLICK_IMPORTANT)
        Then handles long range task memory
        
        :param new_obs: 
        :return: 
        '''
        match self.last_action_and_envtag[0].action_type:
            case Action.Type.STOP:
                return
            case Action.Type.INPUT:
                return
            case Action.Type.CLICK_LINK:
                return
            case Action.Type.CLICK_IMPORTANT:
                # don't do this if new url is diff from old url
                task_eval_prompt = self.__construct_completion_evaluation_prompt(new_obs, model_name = 'gpt-3.5-turbo-0125')
                task_mem = self.__llm_completion_evaluation(task_eval_prompt, model_name = 'gpt-3.5-turbo-0125')
                # task_mem = "Previously failed because requested quantity is unavailable"
                if task_mem != "":
                    EnvironmentChange.change_log[self.last_action_and_envtag[1]] = task_mem
    
        long_range_memory_prompt = self.__llm_long_range_task_memory_prompt(new_obs, model_name = 'gpt-3.5-turbo-0125')
        new_task_mem, new_shrunk_task = self.__call_llm_task_memory(long_range_memory_prompt, model_name = 'gpt-3.5-turbo-0125')
        self.task_memory.append(new_task_mem)
        self.current_subtask = new_shrunk_task
        
        # TODO LONG RANGE TASK MEMORY



    def __call_llm_action(self, prompt, model_name='gpt-3.5-turbo-1106'):
        '''
        Calls the llm to get the next action
        
        :param prompt: 
        :param model_name: 
        :return: 
        '''
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

    def __llm_completion_evaluation(self, prompt, model_name='gpt-3.5-turbo-1106'):
        '''
        llm call to evaluate the completion success of a task

        :param prompt:
        :param model_name:
        :return:
        '''
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
