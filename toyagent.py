import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from openai import OpenAI
from openai import ChatCompletion
import os
from bs4 import BeautifulSoup
import copy


api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

class IntrastateWebPageNode:
    def __init__(self, url=None, edge=None, private=None, acc_tree=None, embedding=None): # represented by url and action, action taken at url/state
        self.url = url
        self.edge = edge # something like (action, html of action)
        self.private = private # effect of edge operation on parent
        self.public = None # functionality of all children operations
        self.parent = None
        self.trajectory = [] # How you got here from root

        self.acc_tree = acc_tree
        self.children = []
        self.page_embedding = embedding

    def add_child(self, child):
        self.children.append(child)
        child.parent = self
        child.trajectory = copy.deepcopy(self.trajectory)
        child.trajectory.append(child.edge)

def deserialize_intrastate(node_data):
    """ Deserialize a node dictionary into an IntrastateWebPageNode object. """
    node = IntrastateWebPageNode(
        url=node_data['url'],
        edge=node_data['edge'],
        private=node_data['private'],
        acc_tree=node_data['acc_tree']
    )

    for child_data in node_data['children']:
        child_node = deserialize_intrastate(child_data)
        node.add_child(child_node)

    return node

def load_intrastate_from_json(filename):
    with open(filename, 'r') as file:
        data = json.load(file)
        return deserialize_intrastate(data)

def print_intrastate(node, indent=0):
    print(' ' * indent + str(node.edge))
    for child in node.children:
        print_intrastate(child, indent + 4)

class WebPageNode:
    def __init__(self, url, private, public, acc_tree, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private if public is None else public
        self.parent = parent
        self.acc_tree = acc_tree
        self.children = children if children is not None else []
        self.page_embedding = embedding

    def add_child(self, child_node):
        child_node.parent = self  # Set this node as the parent of the child
        self.children.append(child_node)

    def to_dict(self):
        return {
            "url": self.url,
            "private": self.private,
            "public": self.public,
            "acc_tree": self.acc_tree,
            "vec_embedding": self.page_embedding,
            "children": [child.to_dict() for child in self.children]
        }

    def __str__(self):
        parent_url = self.parent.url if self.parent else 'None'
        children_urls = ', '.join([child.url for child in self.children])
        return (f"WebPageNode(URL: {self.url}, Private: {self.private}, "
                f"Public: {self.public}, Parent URL: {parent_url}, "
                f"Children URLs: [{children_urls}]")

def deserialize_interstate(node_data, parent=None):
    # Recreate a WebPageNode from the dictionary data.
    node = WebPageNode(
        url=node_data["url"],
        private=node_data["private"],
        public=node_data["public"],
        acc_tree=node_data["acc_tree"],
        embedding=node_data.get("vec_embedding"),
        parent=parent
    )

    for child_data in node_data["children"]:
        child_node = deserialize_interstate(child_data, parent=node)
        node.add_child(child_node)

    return node

def load_interstate_from_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        tree_data = json.load(file)
    return deserialize_interstate(tree_data)



def get_interstate(intent, answers, model_name="gpt-4-1106-preview"):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the intended goal."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. If you choose an answer, you must only choose a single answer. If anything is mentioned in the list of one answer that's more specific than anything mentioned in any other answer, choose that answer, even if that answer if longer and contains far more information and options. "},
        {"role": "system",
         "content": "Reason through your answer step-by-step, giving detailed thoughts in each step. Read through each the list associated with each answer I give you carefully. Give the your final answer like this: \n '''1'''\n Or this: '''13'''\nGIVE ONLY INTEGER NUMBERS INSIDE THIS FORMAT. YOU MUST REPLY WITH THIS FORMAT. "}
    ]

    one_shot = {"role": "system",
         "content": f"Here is an example:\n '''\n Here's the intent: {"TONK"}\n Here are the answers you must choose from: {"TONK"}\n Desired answer: {"TONK"}\n '''"}

    messages.append({"role": "user",
        "content": f"Here's the intent: {intent}\n Here are the answers you must choose from:\n {answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0.0,
        max_tokens=1500
    )

    result = response.choices[0].message.content
    print(f"GPT RAW RETURN: {result}")

    pattern1 = r"\'\'\'(.*?)\'\'\'"
    pattern2 = r"\`\`\`(.*?)\`\`\`"

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




def construct_options_from_children(children):
    result = []
    for i in range(len(children)):
        child = children[i]
        result.append(f"{i+1}: {child.public}\n")
    return result

def get_child_from_index(node, index):
    children = node.children
    return children[index]

def chunk_answers(answers, chunk_size):

    chunked_list = []

    for i in range(0, len(answers), chunk_size):
        chunked_list.append(answers[i:i + chunk_size])

    return chunked_list

def navigate_interstate_bubble(start_node, intent):
    curr_node = start_node
    changed_flag = False
    for _ in range(10):
        curr_node_children = copy.deepcopy(curr_node.children)
        while len(curr_node_children) > 0:
            potential_node = curr_node_children.pop(0)
            bubble = [curr_node, potential_node]
            answers = construct_options_from_children(bubble)
            answer = get_interstate(intent, answers, model_name="gpt-3.5-turbo-1106")
            if answer != "FAILURE" and answer != "N/A":
                index = int(answer) - 1
                curr_node = bubble[index]
                changed_flag = True
        if not changed_flag:
            break

    return curr_node

def navigate_interstate(start_node, intent, chunk_size=None):
    curr_node = start_node
    for _ in range(10):
        answers = construct_options_from_children(curr_node.children)
        if chunk_size != None:
            chunked_answers = chunk_answers(answers, chunk_size)

            possible_results = []

            for chunk in chunked_answers:
                print(f"CHUNK: {chunk}")
                answer = get_interstate(intent, chunk, model_name="gpt-4-1106-preview")
                if answer != "FAILURE" and answer != "N/A":
                    possible_results.append(answer)

            print(f"POSSIBLE RESULTS: {possible_results}")
            print(f"curr_node: {curr_node.url}")

            if len(possible_results) == 0:
                return curr_node
            elif len(possible_results) == 1:
                index = int(possible_results[0]) - 1
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else: # Do recursive in future
                possible_nodes = [get_child_from_index(curr_node, int(result) - 1) for result in possible_results]
                filtered_possible_results = construct_options_from_children(possible_nodes)
                print(f"FILTERED POSSIBLE RESULTS: {filtered_possible_results}")
                answer = get_interstate(intent, filtered_possible_results, model_name="gpt-4-1106-preview")
                if answer != "FAILURE" and answer != "N/A":
                    index = int(answer) - 1
                    child = possible_nodes[index]
                    curr_node = child
                else:
                    break
        else:
            print(f"ANSWERS: {answers}")
            answer = get_interstate(intent, answers, model_name="gpt-4-1106-preview")
            print("NO CUNKING")
            print(f"ANSWER: {answer}")
            if answer != "FAILURE" and answer != "N/A":
                index = int(answer) - 1
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else:
                break
    return curr_node


interstate_tree = load_interstate_from_file('webpage_MVP_V3.json')
intrastate_tree = load_intrastate_from_json('orthosuppliesdraft.json')

intent = "What is the price range of teeth grinding mouth guard in the One Stop Market?"

# end_state = navigate_interstate(interstate_tree, intent, chunk_size=10)
# end_state = navigate_interstate_bubble(interstate_tree, intent)



def do_task(start_node, intent):
    end_state = navigate_interstate(start_node, intent, chunk_size=10)
    print(f"END URL: {end_state.url}")
    print(f"END PUBLIC: {end_state.public}")
    return end_state

do_task(interstate_tree, intent)
