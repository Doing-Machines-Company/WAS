from __future__ import annotations
from memgpt import MemGPT
from use_scrape_utils import *
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

        # Create a MemGPT client object (sets up the persistent state)
        self.client = MemGPT()

        # You can set many more parameters, this is just a basic example
        self.agent_id = self.client.create_agent(
        agent_config={
            "name" : "WebAgentv3",
            "preset" : "agent_preset",
            "persona": "web_agent",
            "human": "basic",
            "model": "gpt-3.5-turbo-0125"
        }
        )

        # Now that we have an agent_name identifier, we can send it a message!
        # The response will have data from the MemGPT agent

        self.last_action_and_envtag = None
        self.impossible_call_result = {'command': None, 'done_something_not_impossible': True}
        self.old_obs = None
        self.to_do_memory = []
        self.already_done_memory = []
        self.current_subtask = None
        self.last_different_page = ((None, None), ("Webshop homepage", "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/"))

        with open('auxillary_jsons/external_links.json', 'r') as file:
            self.all_links = json.load(file)

    def __aggressive_normalize_url(self, url: str):  # Very aggressive normalization
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

    def __soft_normalize_url(self, url):
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme if parsed_url.scheme else 'http'
        netloc = parsed_url.netloc
        path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
        query = parsed_url.query  # Include the query part
        fragment = parsed_url.fragment  # Include the fragment part

        normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
        return normalized_url





    def __construct_elements_prompt(self, cur_obs: AxObservation, model_name: str) -> (str, list[Action]):  # MOSTLY FOR GPT, NEED MORE CODE GEN STABILITY
        '''
        Constructs the prompt for the model to generate a response for get_next_action

        :param cur_obs: 
        :param model_name: 
        :return: 
        '''
        cleaned_tree, action_list = self.__process_axtree(cur_obs)
        print(cleaned_tree)
        input("Look at tree for get next action")

        if model_name.startswith('gpt'):
            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop. I am going to give you a main task, and an accessibility tree of the web page you are on. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. The main task is your overall objective. The current subtask helps you complete the main task. "},
                {"role": "system",
                 "content": "Any information you see on the page is automatically stored in your memory by another agent. Any information on an already visited page has been recorded in your memory be another agent. "},
                {"role": "system",
                 "content": "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. You must give input_string only if the option has 'Input field'. Pay attention to all information enclosed in in parentheses. THIS IS IMPORTANT:\n Action choices without parantheses have not been attempted. "},
                {"role": "system",
                 "content": "An GOOD SUBTASK is a subtask that is essential to the completion of a task. GOOD SUBTASKS are subtasks that must be completed in order for your task to be completed. GOOD SUBTASKs can be completed by a single action on the page. Tasks cannot be completed without completing all GOOD SUBTASKS. Any subtasks that involve discovery or navigation are BAD. "},
                {"role": "system",
                 "content": "First, tell me what page you are currently on, and what can be done on the page that is relevant to your task. First using the information in parentheses, list out all the actions and tasks that have already been completed. If there are no more helpful unvisited options that can be explored and the main task is irrelevant to the page and helpful visit options, option 1 is optimal. If the there are no more helpful unvisited options that can be explored and the main task is impossible, option 1 is optimal. If the current page is relevant to the task, then you MUST generate general GOOD SUBTASKs. "},
                {"role": "system",
                 "content": "Then you must reason step-by-step through all alerts and information in the tree that is enclosed in parentheses, and reason step-by-step to determine if that information indicates that your task has already been completed or if the task is impossible. Then you must reason through the accessibility tree to find unvisited pages which may be helpful. \n"},
                {"role": "system",
                 "content": "Then only if the task is possible and unfinished, you must reason step-by-step through all of your GOOD SUBTASKs to determine the first incomplete GOOD SUBTASK. The optimal action is the first action that completes a subtask that is still incomplete. If the main task has been completed, option 0 is optimal. Finally, you must give me the Python code using the Python function choose_option."}
            ]

            if self.current_subtask:
                messages.append({"role": "user",
                                 f"content": f"This is your main task: {self.intent}\nThis is your current subtask: {self.current_subtask}\nHere is the accessibility tree: \n'''\n {cleaned_tree}\n'''\nReason then write me python code using choose_options. "})
            else:
                messages.append({"role": "user",
                                 f"content": f"This is your main task: {self.intent}\nThis is your current subtask: {self.intent}\nHere is the accessibility tree: \n'''\n {cleaned_tree}\n'''\nReason then write me python code using choose_options. "})

            print(self.intent)
            print(self.current_subtask)
            input("LOOK AT MESSAGES FOR GET NEXT ACTION")

        if model_name.startswith('gemini'):
            messages = (
                 "You are an autonomous agent performing tasks for an user on a webshop. You only work by calling python functions to select an option. I am going to give you a task, and an accessibility tree. Some lines are start with a number in square brackets on the very left, these lines are actions you can select, you must select one action from the accessibility tree that is labeled with a number. "
                 "The accessibility tree is reflective of the layout of the webpage. If an option has '|', pay attention to what's between those lines, it will tell you if an option has already been selected and if an option is required. Do not choose options that are already selected. "
                 "You have the python function choose_option(task_number: int, input_string: Optional[str]) which takes in a number and an optional string. You must call the python function choose_option in your reply. The task_number is the option number you want to choose. THIS IS IMPORTANT: input_string parameter is MUST BE the STRING YOU WANT TO INPUT INTO THE FIELD when the action you select is an action with 'Input field' in it's text. Pay attention to anything that is required."
                 "First look at the task, then look at the task completion progress, then you must generate subtasks using both pieces of information, reasong through these step-by-step. Reason through every single possible action labelled with a number in brackets at the start carefully, step-by-step, to decide which action you should perform first. Do your best to select an answer. If multiple steps are needed, select the first step as your option. Give me the code for choose_option.\n")

            messages += f"This is your current task: {self.intent}\nTask completion progress: DNE FIX THIS!!!!!! \nWhat is the action you will perform? Here is the accessibility tree: \n'''\n {cleaned_tree}\n'''"
        if model_name.startswith('memgpt'):
            messages = (f"OBSERVATION: {cleaned_tree}\nOBJECTIVE: {self.intent}\n ")



        return messages, action_list

    def __construct_completion_evaluation_prompt(self, new_obs: AxObservation,
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
        
        base_tree_cleaned = self.__process_axtree(base_obs, memory=True)
        new_tree_cleaned = self.__process_axtree(new_obs, memory=True)




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


        general_clickables = [
            'menuitem',
             'treeitem', 'switch', 'option', 'menuitemcheckbox',
            'menuitemradio',
            'slider', 'listbox', 'tree',
            'grid',  'alert', 'alertdialog', 'dialog',
            'log', 'marquee', 'timer', 'tooltip', 'banner',
            'complementary', 'contentinfo', 'form', 'main', 'navigation',
            'region', 'status', 'img', 'note', 'application',
            'article', 'cell', 'definition', 'directory', 'document',
            'feed', 'figure', 'group', 'img', 'list',
            'listitem', 'math', 'progressbar',
            'separator', 'toolbar', 'tooltip', 'presentation']

        input_roles = [
            'textbox', 'searchbox', 'slider', 'spinbutton', 'radiogroup',
            'checkbox', 'radio', 'switch', 'option', 'listbox',
            'combobox', 'textarea', 'spinbutton'
        ]
        # Error inputting element: Error: Element is not an <input>, <textarea> or [contenteditable] element

        currently_ignored = ['gridcell', 'columnheader', 'rowheader', 'tab',
            'tabpanel', 'row', 'rowgroup', 'search', 'heading']

        if xpath and html:
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
                    if env_tags and env_tags in EnvironmentChange.change_log:
                        props.append("Already visited")
                        role_name = "Choose to visit another webshop page again: "
                    else:
                        role_name = "Choose to visit another webshop page for the first time: "
                        props.append("Univisited")


                case Action.Type.CLICK_IMPORTANT:
                    role_name = "Choose action: "
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
                    pass

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
        ignored_roles = ["ListMarker", "Image", "LineBreak"]
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
            case Action.Type.CLICK_IMPORTANT:
                if node_info['name'].strip() == 'Search':
                    return True
            case Action.Type.CLICK_LINK:
                href_regex = r'href="([^"]*)"'
                href_values = re.findall(href_regex, node_info['html'])
                if len(href_values) > 0:
                    for href_value in href_values:
                        if href_value.startswith('#') and href_value != '#':
                            return True
                        if self.__aggressive_normalize_url(href_value) in self.all_links and self.__aggressive_normalize_url(href_value) != self.__aggressive_normalize_url(obs_url):
                            return True
            case Action.Type.CLICK_GENERAL:
                href_regex = r'href="([^"]*)"'
                href_values = re.findall(href_regex, node_info['html'])
                if len(href_values) > 0:
                    for href_value in href_values:
                        if href_value.startswith('#') and href_value != '#':
                            return True
                        if self.__aggressive_normalize_url(
                                href_value) in self.all_links and self.__aggressive_normalize_url(
                                href_value) != self.__aggressive_normalize_url(obs_url):
                            return True
            case Action.Type.CLICK_IMPORTANT:
                if "<img src" in node_info['html']:
                    return True
        return False

    def __process_radios(self, radio_nodes: list[(dict, int, (Action, EnvironmentChange))], memory=False):
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
                node_action.set_tree_line(f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']} (this option selected)")
                tree_insert +=  f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']} (this option selected)\n"
                action_list.append((node_action, env_tags))
            elif checked_flag:
                node_action.set_tree_line(f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']}")
                tree_insert +=  f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']}\n"
                action_list.append((node_action, env_tags))
            else:
                node_action.set_tree_line(f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']}")
                tree_insert += f"[{counter if not memory else ''}]{node_info['indent']}       Select: {node_info['name']}\n"
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
    def __get_starting_tree_and_actions(self, obs: AxObservation, memory=False):
        '''
        Gets the starting tree and actions for the prompt
        :return:
        '''
        # TODO back button needs to be fucking fixed

        cleaned_tree = f"[0] Nothing more to do (ONLY CHOOSE when there is nothing else to do)\n[1] Choose ONLY if task is impossible on current page (ONLY CHOOSE if task can't be completed on current page and there are no more helpful visit options)\n"
        action_list = [
            (Action(Action.Type.GET_NEXT_SUBTASK_FINISHED, None, None),
             EnvironmentChange(obs.url, None, Action.Type.GET_NEXT_SUBTASK_FINISHED)),
            (Action(Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE, None, None),
             EnvironmentChange(obs.url, None, Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE)),
        ]
        counter = 2
        if self.last_action_and_envtag:

            if self.last_different_page[0][1] and self.__aggressive_normalize_url(self.last_different_page[0][1]) != self.__aggressive_normalize_url(obs.url):
                cleaned_tree += f"[{counter if not memory else ''}] Go back to page for: {self.last_different_page[0][0]}\n"
                goback_action = Action(Action.Type.GO_BACK, None, None)
                goback_action.set_input_string(copy.deepcopy(self.last_different_page[0][1]))

                action_list.append((goback_action,
                         EnvironmentChange(obs.url, None, Action.Type.GO_BACK)))
                counter += 1



        return cleaned_tree, action_list, counter
    def __process_axtree(self, obs: AxObservation, memory=False):
        '''
        Heavily processes the tree for the prompt
        Skips options via function calls

        :param obs:
        :return:
        '''

        if memory:
            cleaned_tree = ""
            action_list = []
            counter = 0
        else:
            cleaned_tree, action_list, counter = self.__get_starting_tree_and_actions(obs, memory)

        scanning_radios = False


        row_headers = []
        column_headers = []
        current_table_counter = 0
        curr_row = -1
        curr_col = -1

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
                                tree_strings, radio_actions = self.__process_radios(current_radio_nodes, memory)
                                cleaned_tree += tree_strings
                                action_list.extend(radio_actions)
                                current_radio_nodes = []
                        tree_add = f"[{counter if not memory else ''}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

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
                                    tree_strings, radio_actions = self.__process_radios(current_radio_nodes, memory)
                                    cleaned_tree += tree_strings
                                    action_list.extend(radio_actions)
                                    current_radio_nodes = []
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                                else:
                                    tabled_options.add(name_field)
                                    current_radio_nodes.append((obs.nodes_info[i], counter, (node_action, env_tags)))
                        else:
                            tree_add = f"[{counter if not memory else ''}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"


                    else:
                        if scanning_radios:
                            scanning_radios = False
                            if len(current_radio_nodes) > 0:
                                tree_strings, radio_actions = self.__process_radios(current_radio_nodes, memory)
                                cleaned_tree += tree_strings
                                action_list.extend(radio_actions)
                                current_radio_nodes = []
                        tree_add = f"[{counter if not memory else ''}]{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']} {props}\n"

                    counter += 1
                    if tree_add:
                        cleaned_tree += tree_add
                        node_action.set_tree_line(tree_add)
                        action_list.append((node_action, env_tags))
                else:
                    # TODO Do tabling here!
                    if scanning_radios:
                        scanning_radios = False
                        if len(current_radio_nodes) > 0:
                            tree_strings, radio_actions = self.__process_radios(current_radio_nodes, memory)
                            cleaned_tree += tree_strings
                            action_list.extend(radio_actions)
                            current_radio_nodes = []


                    if obs.nodes_info[i]['role'] == 'table':
                        # Initialize a new table
                        column_headers = []
                        row_headers = []
                        curr_row = -1
                        curr_col = -1
                        cleaned_tree += f"{obs.nodes_info[i]['indent']}Table of: {obs.nodes_info[i]['name']}\n"

                    elif obs.nodes_info[i]['role'] == 'caption':
                        continue

                    elif obs.nodes_info[i]['role'] == 'row':
                        curr_row = (curr_row + 1)

                    elif obs.nodes_info[i]['role'] == 'columnheader':
                        column_headers.append(obs.nodes_info[i]['name'])

                    elif obs.nodes_info[i]['role'] == 'rowheader':
                        row_headers.append(obs.nodes_info[i]['name'])

                    elif obs.nodes_info[i]['role'] == 'gridcell':
                        curr_col = (curr_col + 1) % len(column_headers)

                        if curr_row < len(row_headers):
                            row_head = row_headers[curr_row]
                        else:
                            row_head = None

                        if curr_col < len(column_headers):
                            col_head = column_headers[curr_col]
                        else:
                            col_head = None

                        if row_head and col_head:
                            cleaned_tree += f"{obs.nodes_info[i]['indent']}{row_head} and {col_head}: {obs.nodes_info[i]['name']}\n"
                        elif row_head:
                            cleaned_tree += f"{obs.nodes_info[i]['indent']}{row_head}: {obs.nodes_info[i]['name']}\n"
                        elif col_head:
                            cleaned_tree += f"{obs.nodes_info[i]['indent']}{col_head}: {obs.nodes_info[i]['name']}\n"
                        else:
                            cleaned_tree += f"{obs.nodes_info[i]['indent']}Option: {obs.nodes_info[i]['name']}\n"
                    else:
                        cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                if obs.nodes_info[i]['name'].strip != "":
                    cleaned_tree += f"{obs.nodes_info[i]['indent']}You are currently on the page for:\n {obs.nodes_info[i]['name']}\n"
                    if self.__aggressive_normalize_url(self.last_different_page[1][1]) != self.__aggressive_normalize_url(obs.url):
                        self.last_different_page = (self.last_different_page[1], (obs.nodes_info[i]['name'], obs.url)) # TODO CHECK DIFFERENT PAGE IF NOT NONE


                # input('finshed processing tree')

        if scanning_radios:
            scanning_radios = False
            if len(current_radio_nodes) > 0:
                tree_strings, radio_actions = self.__process_radios(current_radio_nodes, memory)
                cleaned_tree += tree_strings
                action_list.extend(radio_actions)
                current_radio_nodes = []
        if memory:
            return cleaned_tree
        return cleaned_tree, action_list

    def __process_axtree_noaction(self, obs: AxObservation):
        '''
        Heavily processes the tree for the prompt
        Skips options via function calls

        :param obs:
        :return:
        '''
        cleaned_tree = ""

        for i in range(len(obs.nodes_info)):
            if self.__skip_option(obs.nodes_info[i]):
                continue
            if obs.nodes_info[i]['role'] != 'RootWebArea':
                node_action = self.__extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'], obs.nodes_info[i]['role'], obs.url)

                if node_action:
                    pass
                    tree_add = None
                    if self.__skip_action(obs.nodes_info[i], node_action, obs.url):
                        continue

                    role_name = obs.nodes_info[i]['role'] + ": "

                    if node_action.action_type == Action.Type.INPUT:
                        tree_add = f"{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']}\n"

                    elif node_action.action_type == Action.Type.CLICK_RADIO:
                        pass

                    elif node_action.action_type == Action.Type.CLICK_CHECKBOX:
                        pass

                    else:
                        tree_add = f"{obs.nodes_info[i]['indent']}{role_name}{obs.nodes_info[i]['name']}\n"

                    if tree_add:
                        cleaned_tree += tree_add
                        node_action.set_tree_line(tree_add)
                elif obs.nodes_info[i]['role'].strip() != 'generic':
                    cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}You are currently on the page for: {obs.nodes_info[i]['name']}\n"

        return cleaned_tree


    def __get_desired_url(self, chunk_size=20):
        '''
        Used for GOTO_URL

        :param chunk_size:
        :return:
        '''
        start_node = get_GOTO_tree('auxillary_jsons/webtreeflattened_noprods.json')
        if self.current_subtask:
            intent = self.current_subtask
        else:
            intent = self.intent
        def get_desired_url_helper(intent, answers, model_name="gpt-4-1106-preview"):

            messages = [
                {"role": "system",
                 "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the task, or is needed or contains information to help you achieve your goal. "},
                {"role": "system",
                 "content": "If there are multiple possible answers, you must choose one. THIS IS IMPORTANT: Ignore any emphasis, you only care about what is mentioned in each answer choice, the amount or emphasis of items in the list does not matter. "},
                {"role": "system",
                 "content": "You have the Python function choose_page(task_number: int|None). If you choose an answer, you must only choose a single answer. If none of the options are valid, call the function with None. The task_number is the option number you want to choose. "},
                {"role": "system",
                 "content": "First you MUST reason through EVERY option I give you step-by-step thoughtfully. Give explanations for why every option I give you may be right or wrong. YOU MUST try your best to choose an answer. If one option may lead to more information or something to help you complete your task, it is a valid choice. THIS IS IMPORTANT: \nYOU MUST GIVE ME final answer USING the python function choose_page. "},
            ]

            formatted_answers = '\n'.join(answers)
            messages.append({"role": "user",
                             "name": "user",
                             "content": f"Task: {intent}\nHere are the possible answers:\n {formatted_answers}\n"})

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
            print(result)
            input("URL HELPER RESULT")


            pattern = r"choose_page\(([0-9]+)\)"


            matches = re.findall(pattern, result)

            for match in matches:
                return match
            print("getting links failed")

        def construct_options_from_children(children):
            result = []
            for i in range(len(children)):
                child = children[i]
                result.append(f"{i}) {child.public}\n")
            return result

        def get_child_from_index(node, index):
            children = node.children
            return children[index]

        def chunk_answers(answers, chunk_size):

            chunked_list = []

            for i in range(0, len(answers), chunk_size):
                chunked_list.append(answers[i:i + chunk_size])

            return chunked_list

        curr_node = start_node
        for _ in range(10):
            answers = construct_options_from_children(curr_node.children)
            chunked_questions = chunk_answers(answers, chunk_size)

            possible_results = []

            for chunk in chunked_questions:
                answer = get_desired_url_helper(intent, chunk, model_name="gpt-3.5-turbo-0125")
                if answer and answer != "None":
                    possible_results.append(answer)

            if len(possible_results) == 0:
                return None
            elif len(possible_results) == 1:
                child = get_child_from_index(curr_node, int(possible_results[0]))
                curr_node = child
                if len(curr_node.children) == 0:
                    return curr_node.url
            else:  # Do recursive in future
                possible_nodes = [get_child_from_index(curr_node, int(result)) for result in possible_results]
                filtered_possible_results = construct_options_from_children(possible_nodes)
                answer = get_desired_url_helper(intent, filtered_possible_results, model_name="gpt-3.5-turbo-0125")
                if answer != "FAILURE" and answer != "N/A":
                    index = int(answer)
                    child = possible_nodes[index]
                    curr_node = child
                    if len(curr_node.children) == 0:
                        return curr_node.url
                else:
                    return None
        return None
    def get_next_action(self, cur_obs: AxObservation) -> Action:
        '''
        Gets the next action to perform
        
        :param cur_obs: 
        :return: 
        '''

        self.old_obs = cur_obs
        prompt_for_agent, answer_values = self.__construct_elements_prompt(cur_obs, model_name = 'gpt-3.5-turbo-0125') # prompt_for_agent: str, answer_values: list[Actions]

        if self.impossible_call_result['command'] != None:
            match self.impossible_call_result['command']:
                case Action.Type.STOP:
                    desired_action = Action(Action.Type.STOP, None, None)
                    env_change = EnvironmentChange(cur_obs.url, None, Action.Type.STOP)
                    self.last_action_and_envtag = (desired_action, env_change)

                case Action.Type.GOTO_URL:
                    desired_action = Action(Action.Type.GOTO_URL, None, None)
                    desired_url = self.__get_desired_url()
                    desired_action.set_input_string(desired_url)
                    env_change = EnvironmentChange(cur_obs.url, None, Action.Type.GOTO_URL)
                    self.last_action_and_envtag = (desired_action, env_change)

            self.impossible_call_result['command'] = None
            assert(self.impossible_call_result['done_something_not_impossible'] == False)



        else:
            (final_index, final_string) = self.__call_llm_action(prompt_for_agent, model_name = 'gpt-3.5-turbo-0125')
            if final_index and final_index != -1:
                desired_action = answer_values[int(final_index)][0]
                self.last_action_and_envtag = answer_values[int(final_index)]
                new_change = answer_values[int(final_index)][1]

                if desired_action.action_type == Action.Type.INPUT:
                    desired_action.set_input_string(final_string)
                    EnvironmentChange.change_log[new_change] = desired_action.input_string
                elif desired_action.action_type == Action.Type.CLICK_LINK:
                    EnvironmentChange.change_log[new_change] = None

                if desired_action.action_type != Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE:
                    self.impossible_call_result['done_something_not_impossible'] = True



        if desired_action:
            return desired_action

        return Action(Action.Type.STOP, None, None) # TODO HANDLE FAILED GPT RETURNS BETTER

    def __llm_get_important_subtask_prompt(self, new_obs: AxObservation, model_name: str) -> list[dict]: # TODO NEED TO FORCE LONGER OUTPUT
        '''
        Can info memory retrieve everything that is necessary?
        In essence, you want to store all the important subtasks that are not yet completed, especially if they have identifying information

        :param new_obs:
        :param model_name:
        :return:
        '''

        cleaned_tree = self.__process_axtree(new_obs, memory=True)
        # cleaned_tree = self.__process_axtree_noaction(new_obs)

        if model_name.startswith('gpt'):

            messages = [
                {"role": "system",
                 "content": "You are an agent management specialist for a shopping website. You act as support for an agent completing a goal. "},
                {"role": "system",
                 "content": "You have one Python function here_are_good_subtasks(gathered_good_subtasks: str|None) that takes in a string or None. "},
                {"role": "system",
                 "content": "SUBTASKs are tasks that MUST be completed in order for the main goal to be completed. "},
                {"role": "system",
                 "content": "I am going to give you the agent's main goal, a list of IMPORTANT SUBTASKs already gathered for the goal, and an accessibility tree of the web page the agent is currently on. "},
                {"role": "system",
                 "content": "THESE THINGS ARE IMPORTANT: \n1) A GOOD SUBTASK MUST help you complete the agent's main goal. \n2) A GOOD SUBTASK is general and ONLY contain actions. \n3) A GOOD SUBTASK is very general and does not contain any numbers or decriptives or specific information or specific website actions. \n4) A GOOD SUBTASK only uses action words similar to the action words the main goal uses. "},
                {"role": "system",
                 "content": "Any SUBTASK that is irrelevant to your main goal is a BAD SUBTASK. A SUBTASK that is a duplicate of something in the list I give you is BAD. "},
                {"role": "system",
                 "content": "THIS IS IMPORTANT: SUBTASKs relating to storing/recording information are BAD. SUBTASKs relating to filtering are BAD. "},
                {"role": "system",
                 "content": "THIS IS IMPORTANT: \n1)DO NOT PASS SPECIFIC INFORMATION LIKE SKUs, dates, and order numbers through here_are_good_subtasks. \n2) gathered_good_subtasks DOES NOT contain any numbers or decriptives or specific information. \n3) gathered_good_subtasks does not quote specific website actions. "},
                {"role": "system",
                 "content": "First you must reason through the accessibility tree and list out EVERY SINGLE SUBTASK that may help you complete your main goal. Secondly, you must go through these SUBTASKs and keep the general SUBTASKs. Thirdly, you must reason through the list SUBTASKs I ALREADY KNOW ABOUT I'm going to give you, then make sure that you are only giving me new GOOD SUBTASKs. Fourthly, you must reason one-by-one through these SUBTASKs to identify which SUBTASKs are GOOD. Fifthly, reason through your GOOD SUBTASKs and choose the first GOOD SUBTASK that is not in SUBTASKs I ALREADY KNOW ABOUT. Finally, if you have a GOOD SUBTASK, formulate gathered_good_subtasks to pass here_are_good_subtasks using action words similar to the action words the agent's 'Main goal' uses. Then pass the string you formualted for gathered_good_subtasks into here_are_good_subtasks directly without using variables. "}

            ]
            subtasks_list = copy.copy(self.to_do_memory)
            subtasks_list.append("All GOOD SUBTASKs that can be completed STAYING ON the current page are already known.")
            messages.append({"role": "user",
                             "content": f"Main goal: {self.intent}\nSUBTASKs I ALREADY KNOW ABOUT: {subtasks_list}\nCurrent page accessibility tree: \n'''\n {cleaned_tree}\n'''\nYOU MUST FIRST reason as instructed, and only AFTER REASONING you must then write me the python code using here_are_good_subtasks."})
            return messages

    def __llm_get_important_subtask_call(self, prompt: list[dict], model_name: str) -> str:
        '''
                llm call to gather important subtasks from a page

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
                seed=818181818
            )
            result = response.choices[0].message.content
            pattern1 = r"here_are_good_subtasks\(\"(.*?)\"\)"
            pattern2 = r"here_are_good_subtasks\(\'(.*?)\'\)"

            # Searching the LLM output for the pattern
            matches1 = re.findall(pattern1, result)
            matches2 = re.findall(pattern2, result)
            print("IMPORTANT SUBTASK REASONING")
            print(result)
            input("LOOK AT IMPORTANT SUBTASK REASONING")

            if len(matches1) > 0:
                for match in matches1:
                    return match.strip()
            elif len(matches2) > 0:
                for match in matches2:
                    return match.strip()


    def __llm_next_task_finished_prompt(self, model_name: str) -> list[dict]: # TODO BROKEN AS FUCK
        if model_name.startswith('gpt'):
            messages = [{
                    "role": "system",
                    "content": "You are a management specialist for a shopping website. You act as support for an agent. "
                },
                {
                    "role": "system",
                    "content": "An IMPORTANT SUBTASK is a subtask that is essential to the completion of a goal. IMPORTANT SUBTASKs are subtasks that must be completed in order for the main goal to be completed. Tasks cannot be completed without completing all IMPORTANT SUBTASKs. Any subtasks that involve discovery or navigation are UNIMPORTANT. IMPORTANT SUBTASKs are general. An IMPORTANT SUBTASK can be completed in an arbitrary number of steps. If an IMPORTANT SUBTASK can be decomposed into multiple similar IMPORTANT SUBTASKs, you must decompose it. "
                },
                {
                    "role": "system",
                    "content": "IDENTIFYING INFORMATION are pieces of information which are essential to complete IMPORTANT SUBTASKs. IDENTIFYING INFORMATION includes dates, product SKUs, order numbers and other specific information. "
                },
                {
                    "role": "system",
                    "content": "I am going to give you the main goal the agent is working on, a list of all IMPORTANT SUBTASKS that need to be completed and a list of completed IMPORTANT SUBTASKS. "
                },
                {
                    "role": "system",
                    "content": "You have one Python function issue_subtask(next_important_subtask: str) that takes in a string. next_important_subtask is a string which details the next IMPORTANT SUBTASKs that need to be completed with all IDENTIFYING INFORMATION needed to complete those IMPORTANT SUBTASKs. "
                },
                {
                    "role": "system",
                    "content": "Now you must reason step-by-step through the list of all IMPORTANT SUBTASKS and the list of completed IMPORTANT SUBTASKS to determine the next IMPORTANT SUBTASK that needs completing. Then reason step-by-step to see if the action can be decomposed into multiple similar IMPORTANT SUBTASKs. next_important_subtask is detailed information with IDENTIFYING INFORMATION about this next IMPORTANT SUBTASK after it is decomposed if necessary. THIS IS IMPORTANT, if the goal has been completed or if there are no IMPORTANT SUBTASKs, your next_importan_subtask must be \"Stop\"."
                }
            ]
            messages.append({"role": "user",
                            "content": f"Main goal: {self.intent}\nAll IMPORTANT SUBTASKs: {self.to_do_memory}\nAll completed IMPORTANT SUBTASKs: {self.already_done_memory}\nGive me the Python code using the issue_subtask function with the parameter passed directly. "})

            print(f"Main goal: {self.intent}\nAll IMPORTANT SUBTASKs: {self.to_do_memory}\nAll completed IMPORTANT SUBTASKs: {self.already_done_memory}\nGive me the Python code using the issue_subtask function with the parameter passed directly. ")
            input("LOOK AT PROMPT FOR issue_subtask")
            return messages


    def __llm_long_next_task_impossible_prompt(self, model_name: str) -> list[dict]:
        if model_name.startswith('gpt'):
            current_tree = self.__process_axtree(self.old_obs, memory=True)
            messages = [{
                    "role": "system",
                    "content": "You are a management specialist for a shopping website. You act as support for an agent. The agent has just failed a task and you are to help them. "
                },
                {
                    "role": "system",
                    "content": "An IMPORTANT SUBTASK is a subtask that is essential to the completion of a goal. IMPORTANT SUBTASKs are subtasks that must be completed in order for the main goal to be completed. Tasks cannot be completed without completing all IMPORTANT SUBTASKs. Any subtasks that involve discovery or navigation are UNIMPORTANT. IMPORTANT SUBTASKs are general tasks. "
                },
                {
                    "role": "system",
                    "content": "I am going to give you the current IMPORTANT SUBTASK the agent failed on and the current page's accessibility tree. "
                },
                {
                    "role": "system",
                    "content": "I am giving you two python functions, do_magic() and stop_now() that both take in nothing. "
                },
                {
                    "role": "system",
                    "content": "There are ONLY TWO possible cases: \nCase 1: The agent failed because the task is impossible to complete on the current page because the current page's purpose does not align with the current IMPORTANT SUBTASK. \nCase 2: The page's purpose does align with the current IMPORTANT SUBTASK. "
                },
                {
                    "role": "system",
                    "content": "First you must reason through the current page accessibility tree to determine the page's purpose. If the page's is meant to complete the current IMPORTANT SUBTASK, you have Case 2. If the page is mostly irrelevant to the current IMPORTANT SUBTASK, then you have Case 1. Then determine which case you have. "
                },
                {
                    "role": "system",
                    "content": "If you have Case 1, you must call the do_magic function. If you have Case 2, you must call the stop_now function. "
                }

            ]
            if self.current_subtask:
                messages.append({"role": "user",
                                 "content": f"Current IMPORTANT SUBTASK that the failed on: {self.current_subtask}\nCurrent page accessibility tree: \n{current_tree}\nGive me the python code using ONLY ONE of the functions I gave you. "})
            else:
                messages.append({"role": "user",
                                 "content": f"Current IMPORTANT SUBTASK that the failed on: {self.intent}\nCurrent page accessibility tree: \n{current_tree}\nGive me the python code using ONLY ONE of the functions I gave you. "})
            return messages

    def __llm_long_next_task_impossible_call(self, prompt, model_name: str) -> Action.Type:
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
            print(result)
            input("impossible call look")
            if "do_magic" in result: # This starts the GOTO URL process
                return Action.Type.GOTO_URL
            elif "stop_now" in result:
                return Action.Type.STOP

    def __llm_long_next_task_finished_call(self, prompt, model_name: str) -> (str, str):
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
                max_tokens=4000,
                # top_p=0,
                seed=12345678
            )
            result = response.choices[0].message.content
            print(f"Finished conclusion: {result}")
            input("LOOK AT IMPORTANT SUBTASK")
            pattern1 = r"issue_subtask\(\"(.*?)\"\)"
            pattern2 = r"issue_subtask\(\'(.*?)\'\)"

            # Searching the LLM output for the pattern
            matches1 = re.findall(pattern1, result)
            matches2 = re.findall(pattern2, result)

            if len(matches1) > 0:
                for match in matches1:
                    return match.strip()
            elif len(matches2) > 0:
                for match in matches2:
                    return match.strip()

    def handle_memory(self, new_obs: AxObservation): # new_obs could be None if last_action was not CLICK_IMPORTANT
        '''
        Handles memory
        First judges task completion if the last action was a button (CLICK_IMPORTANT)
        Then handles long range task memory

        GET_NEXT_SUBTASK variants assume that any potential new subtasks from the page are already stored, so all they need to do is either get the next subtask or decompose
        
        :param new_obs: 
        :return: 
        '''
        if self.last_action_and_envtag:
            if self.last_action_and_envtag[0].action_type != Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE:
                self.impossible_call_result = {'command': None, 'done_something_not_impossible': True}

            match self.last_action_and_envtag[0].action_type:
                case Action.Type.STOP:
                    return
                case Action.Type.INPUT:
                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name='gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name='gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

                case Action.Type.CLICK_GENERAL:
                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name='gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name='gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

                case Action.Type.CLICK_LINK:
                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name = 'gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name = 'gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

                case Action.Type.CLICK_IMPORTANT:
                    # don't do this if new url is diff from old url
                    task_eval_prompt = self.__construct_completion_evaluation_prompt(new_obs, model_name = 'gpt-3.5-turbo-0125')
                    task_mem = self.__llm_completion_evaluation(task_eval_prompt, model_name = 'gpt-3.5-turbo-0125')
                    # task_mem = "Previously failed because requested quantity is unavailable"
                    if task_mem != "":
                        EnvironmentChange.change_log[self.last_action_and_envtag[1]] = task_mem

                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name='gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name='gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

                case Action.Type.GET_NEXT_SUBTASK_FINISHED:

                    if self.current_subtask == None: # TODO this is jank, self.intent is poorly semantically formatted for a llm
                        self.already_done_memory.append(self.intent)
                    else:
                        self.already_done_memory.append(self.current_subtask)

                    long_range_memory_prompt = self.__llm_next_task_finished_prompt(model_name = 'gpt-3.5-turbo-0125')
                    new_to_do = self.__llm_long_next_task_finished_call(long_range_memory_prompt, model_name = 'gpt-3.5-turbo-0125')
                    self.current_subtask = new_to_do

                    # TODO HANDLE NEW TO DO AND SHRUNK TASK
                case Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE:
                    if self.impossible_call_result['done_something_not_impossible'] == True:
                        long_range_memory_prompt = self.__llm_long_next_task_impossible_prompt(model_name='gpt-3.5-turbo-0125')
                        self.impossible_call_result['command'] = self.__llm_long_next_task_impossible_call(long_range_memory_prompt,
                                                                                 model_name='gpt-3.5-turbo-0125')
                        self.impossible_call_result['done_something_not_impossible'] = False
                    elif self.impossible_call_result['done_something_not_impossible'] == True:
                        self.impossible_call_result['command'] = Action.Type.STOP

                case Action.Type.GOTO_URL:
                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name='gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name='gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

                case Action.Type.GO_BACK:
                    important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                                       model_name='gpt-3.5-turbo-0125')
                    important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                              model_name='gpt-3.5-turbo-0125')

                    if important_subtask and important_subtask.strip() != "None":
                        self.to_do_memory.append(important_subtask)
                    if self.current_subtask == None:
                        self.current_subtask = important_subtask

        else:
            important_subtask_prompt = self.__llm_get_important_subtask_prompt(new_obs,
                                                                               model_name='gpt-3.5-turbo-0125')
            important_subtask = self.__llm_get_important_subtask_call(important_subtask_prompt,
                                                                      model_name='gpt-3.5-turbo-0125')

            if important_subtask and important_subtask.strip() != "None":
                self.to_do_memory.append(important_subtask)
            if self.current_subtask == None:
                self.current_subtask = important_subtask



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
                max_tokens=4096,
                # top_p=0,
                seed=12345678
            )
            
            result = response.choices[0].message.content
            print(f"NEXT ACTION RAW: {result}")

            pattern = r'choose_option\((\d+),?\s*(?:\'([^\']*)\'|"([^"]*)"|None)?\)'

            # Searching the LLM output for the pattern
            matches = re.findall(pattern, result)
            for match in matches:
                task_number, input_string_single, input_string_double = match[:3]
                input_string = input_string_single or input_string_double or ""
                return task_number, input_string
        elif model_name.startswith('gemini'):
            GOOGLE_API_KEY = 'AIzaSyBu8ecdjq4gzAGbT5Tk-bQm38S0WZikyDs'
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
            # Generate the response
            response = model.generate_content(prompt)

            # Introduce a delay of 1 second to limit to 60 requests per minute
            #time.sleep(1)

            # Return the text response
            if len(response.candidates) > 0:
                response = response.candidates[0].content.parts[0].text.strip()
            else:
                response = response.text.strip()
            result = response
            print(f"NEXT ACTION RAW: {result}")

            pattern = r'choose_option\((\d+),?\s*(?:\'([^\']*)\'|"([^"]*)"|None)?\)'

            # Searching the LLM output for the pattern
            matches = re.findall(pattern, result)
            for match in matches:
                task_number, input_string_single, input_string_double = match[:3]
                input_string = input_string_single or input_string_double or ""
            return task_number, input_string
        elif model_name.startswith('memgpt'):
            response = self.client.user_message(agent_id=self.agent_id.id, message=prompt)
            
            for r in response:
                if "assistant_message" in r:
                    result  = r["assistant_message"]
                if "internal_monologue" in r:
                    print("Internal Monologue: ", r["internal_monologue"])
            print(f"NEXT ACTION RAW: {result}")

            pattern = r'^\d+:(?:\s*\S.*)?$'

            # Searching the LLM output for the pattern
            match = re.findall(pattern, result)[0]
            task_number, input_string = match.split(":")
            return task_number, input_string.strip()

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
