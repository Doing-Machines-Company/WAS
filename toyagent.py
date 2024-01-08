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

with open('all_links2.json', 'r') as file:
    all_links = json.load(file)

def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')

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


def extract_interaction_info(html): #use general input type
    if '<a' in html:
        return "link"
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and ("<div" not in html): # filter out div?
        # or "select" in html DOESN'T HANDLE
        return "button"
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html:
        return "input"
    if "type=\"checkbox\"" in html:
        return "checkbox"
    return "Uncased Element"

def get_visible_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(strip=True)


def extract_info_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    outer_element = soup.find()  # Find the first/outermost tag

    if outer_element:
        info = {
            'tag': outer_element.name,
            'visible_text': outer_element.get_text(strip=True),
            'interaction': extract_interaction_info(str(outer_element)),
            'attributes': outer_element.attrs,
            'raw_html': html # TODO: Remove this later
        }
        return info
    else:
        return None



def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    query = parsed_url.query  # Include the query part
    fragment = parsed_url.fragment  # Include the fragment part

    normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
    return normalized_url

async def parse_and_clean_new(elements, parent_node):
    cleaned_output = []
    for element in elements:
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")

        if not await element.is_visible() or await element.is_hidden():
            continue
        if await element.is_disabled() or "disabled=\"disabled\"" in html:
            continue
        if href and (href.startswith('#') or normalize_url(href) in all_links or (url_depth(normalize_url(href)) <= 1 and href.endswith(".html"))):
            continue
        if parent_node.parent and href and parent_node.parent.url == normalize_url(href):
            continue
        if "type='hidden'" in html or 'type="hidden"' in html:
            continue

        xpath = await element.evaluate('''(element) => {
            const getElementXPath = (el) => {
                if (!el || el.nodeType !== 1) return '';
                if (el.id) return 'id("' + el.id + '")';
                var path = '', parent = el.parentNode;
                while (parent) {
                    var index = 1, sibling = parent.firstChild;
                    while (sibling) {
                        if (sibling === el) break;
                        if (sibling.nodeType === 1 && sibling.tagName === el.tagName) index++;
                        sibling = sibling.nextSibling;
                    }
                    path = '/' + el.tagName + '[' + index + ']' + path;
                    el = parent; parent = parent.parentNode;
                }
                return path.substring(1);
            };
            return getElementXPath(element);
        }''')

        interaction_info = extract_interaction_info(html)
        visible_text = get_visible_from_html(html)

        # Determine if the element is part of a table and capture the row context
        table_context_with_headers = None
        if interaction_info in ["link", "button", "input"]:  # Check if element types usually in tables
            table_context_with_headers = await element.evaluate('''(element) => {
                        let row = element.closest('tr');
                        let headers = [];
                        let dataWithHeaders = {};
                        if (row) {
                            let table = row.closest('table');
                            if (table) {
                                // Get the headers (assuming the headers are in the first row or in <thead>)
                                let headerCells = table.querySelectorAll('thead th') || table.querySelectorAll('tr:first-child th');
                                headerCells.forEach((th, index) => {
                                    headers[index] = th.textContent.trim();
                                });

                                // Get the data in the same row as the element, excluding interactable elements
                                let dataCells = row.querySelectorAll('td');
                                dataCells.forEach((td, index) => {
                                    let clonedCell = td.cloneNode(true);
                                    // Remove interactable elements from the cloned cell
                                    clonedCell.querySelectorAll('a, button, input, select, textarea, [onclick], [role="button"]').forEach(interactable => interactable.remove());
                                    let header = headers[index] || `Column ${index + 1}`;
                                    let cellText = clonedCell.textContent.trim();
                                    if (cellText) {
                                        dataWithHeaders[header] = cellText;
                                    }
                                });
                            }
                        }
                        return dataWithHeaders;
                    }''')
        if table_context_with_headers == dict() or table_context_with_headers == {}:
            table_context_with_headers = None

        element_info = {
            'xpath': xpath,
            'interaction_info': interaction_info,
            'html': html,
            'visible_text': visible_text,
            'table_context': table_context_with_headers
        }
        cleaned_output.append(element_info)

    return cleaned_output

async def get_usable_elements_new(page, leaf): # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean_new(interactable_elements, leaf)
    return cleaned_elements


def get_interstate(intent, answers, model_name="gpt-4-1106-preview"):

    print(f"INTENT: {intent}")
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a list of functionalities associated with a separate web page. Your are to choose a web page which best fits the intended goal."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. If you choose an answer, you must only choose a single answer. You only care about what is mentioned in each answer choice, the amount or emphasis of items in the list does not matter. Ignore any emphasis."},
        {"role": "system",
         "content": "Reason through your answer step-by-step, giving detailed thoughts in each step. Read through each the list associated with each answer I give you carefully. Give the your final answer like this: \n '''1'''\n Or this: '''13'''\nGIVE ONLY INTEGER NUMBERS INSIDE THIS FORMAT. YOU MUST REPLY WITH THIS FORMAT."},
    ]

    messages.append({"role": "user",
        "content": f"Task: {intent}\nChoose from these answers:\n {answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
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


def get_intrastate(intent, answers, model_name="gpt-4-1106-preview"):

    print(f"INTENT: {intent}")
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop by doing Question and Answer tasks. I am going to give you a task, and an enumerated set of possible answers. Each answer is a description generated from the HTML of an actionable element, as well as a description of what that element does when you choose it if available. "},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' as the input. "},
        {"role": "system",
         "content": "Reason through your answer step-by-step, giving detailed thoughts in each step. Give the your final answer like this: \n '''1'''\n Or this: '''13'''\nGIVE ONLY INTEGER NUMBERS INSIDE THIS FORMAT. YOU MUST REPLY WITH THIS FORMAT. "},
    ]

    messages.append({"role": "user",
        "content": f"Task: {intent}\nChoose from these answers:\n {answers}"})

    response = client.chat.completions.create(
        model=model_name,
        # model="gpt-3.5-turbo-1106",
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


def construct_options_from_children(children):
    result = []
    for i in range(len(children)):
        child = children[i]
        result.append(f"{i}: {child.public}\n")
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
                index = int(answer)
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
                index = int(possible_results[0])
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else: # Do recursive in future
                possible_nodes = [get_child_from_index(curr_node, int(result)) for result in possible_results]
                filtered_possible_results = construct_options_from_children(possible_nodes)
                print(f"FILTERED POSSIBLE RESULTS: {filtered_possible_results}")
                answer = get_interstate(intent, filtered_possible_results, model_name="gpt-4-1106-preview")
                if answer != "FAILURE" and answer != "N/A":
                    index = int(answer)
                    child = possible_nodes[index]
                    curr_node = child
                else:
                    break
        else:
            # print(f"ANSWERS: {answers}")
            answer = get_interstate(intent, answers, model_name="gpt-4-1106-preview")
            print(f"ANSWER: {answer}")
            if answer != "FAILURE" and answer != "N/A":
                index = int(answer)
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else:
                break
    return curr_node


interstate_tree = load_interstate_from_file('webpage_MVP_V4.json')
intrastate_tree = load_intrastate_from_json('myordersdraft.json')

# intent = "What is the price range of wireless earphone in the One Stop Market?"
intent = "What is the date when I made my first purchase on this site?"
# intent = "What is the price range of teeth grinding mouth guard in the One Stop Market?"

# end_state = navigate_interstate(interstate_tree, intent, chunk_size=10)
# end_state = navigate_interstate_bubble(interstate_tree, intent)

async def step_by_xpath(page, edge):
    interaction_info, generated_text, html, xpath = edge
    print(f"STEPPING: Interaction info: {interaction_info}\n HTML: {html}")
    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')

    count = await locator.count()
    if count == 0:
        print(f"STEPPING: No elements found with this xpath: {xpath}")
        # print("IMPOSSIbLE BAD")
        return
    elif count == 1:
        print('STEPPING: One element found with this xpath')
    else:
        print('STEPPING: Multiple elements found with this xpath')


    if interaction_info in ['button', 'click']:
        await page.wait_for_load_state('networkidle')
        locator.first.click()
        await page.wait_for_load_state('networkidle')
    elif interaction_info == 'input':
        await page.wait_for_load_state('networkidle')
        await locator.first.fill(generated_text)

        await page.wait_for_load_state('networkidle')

        await page.keyboard.press('Enter')

        await page.wait_for_load_state('networkidle')

    else:
        print("FUCK3")


def match_edges_with_extracted_info(node, extracted_info):
    matched_edges = []

    for info in extracted_info:
        found = False
        new_info = {
            'visible_text': info['visible_text'],
            'interaction': info['interaction'],
            'attributes': info['attributes'],
        }

        for i in range(len(node.children)):
            edge = node.children[i].edge
            interaction_info, generated_text, html, xpath, visible_text = edge
            if visible_text and visible_text == info['visible_text']:
                # print("FLAG 1")
                matched_edges.append((new_info, f"ACTION DESCRIPTION: {node.children[i].private}"))
                found = True
                break

        if not found:
            for i in range(len(node.children)):
                edge = node.children[i].edge
                interaction_info, generated_text, html, xpath, visible_text = edge
                if html and html == info['raw_html']:
                    matched_edges.append((new_info, f"ACTION DESCRIPTION: {node.children[i].private}"))
                    found = True
                    break
        if not found: matched_edges.append((new_info, "ACTION DESCRIPTION: UNKNOWN"))

    return matched_edges

async def do_task(start_node, intent):
    # end_state = navigate_interstate(start_node, intent, chunk_size=None)
    # print(f"END URL: {end_state.url}")
    # print(f"END PUBLIC: {end_state.public}")
    # Assume we are at order history page

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        # await page.goto(end_state.url) # TODO end_state.url
        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history")




        # TODO Not as simple, have to match usable actions with intrastate options
        usable = await get_usable_elements_new(page, intrastate_tree) # element_info = (xpath, interaction_info, html, visible_text)

        '''
        usable elements
        element_info = {
            'xpath': xpath,
            'interaction_info': interaction_info,
            'html': html,
            'visible_text': visible_text,
            'table_context': table_context_with_headers
        }
        
        '''

        tables = [item['table_context'] for item in usable]
        htmls = [item['html'] for item in usable]
        extracted_info = [extract_info_from_html(html) for html in htmls]


        print("EXTRACTED INFO")
        matched = match_edges_with_extracted_info(intrastate_tree, extracted_info)
        print("MATCHED")
        print(matched)

        print(len(matched))
        print(len(tables))
        # question_for_gpt = [f"{i}) {item}\n" for i, item in enumerate(matched)]
        # print('\n'.join(question_for_gpt))

        '''
        
        edge_info = (interaction_info, generated_text, html, xpath, visible_text)
        private = diff from parent to child
        
        def deserialize_intrastate(node_data):
            node = IntrastateWebPageNode(
                url=node_data['url'],
                edge=node_data['edge'],
                private=node_data['private'],
                acc_tree=node_data['acc_tree'])
        
        '''


    return None

asyncio.run(do_task(interstate_tree, intent))