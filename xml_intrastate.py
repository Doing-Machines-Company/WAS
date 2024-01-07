import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from openai import OpenAI
import os
from bs4 import BeautifulSoup
import copy


api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

all_htmls = []

all_creates_trees = []

with open('all_links.json', 'r') as file:
    all_links = json.load(file)

user_context = {
    "email": "emma.lopez@gmail.com",
    "password": "Password.123",
    "first_name": "Emma",
    "last_name": "Lopez",
    "address": "1234 Main St",
    "city": "San Francisco",
    "state": "California",
    "zip": "94101",
    "phone": "1234567890",
    "cc_number": "1234567890123456",
    "cc_exp_month": "01",
    "cc_exp_year": "2022",
    "cc_cvv": "123",
    "desired_product": "Tennis Balls 24 count",
    "desired_price": "$12.00",
    "desired_amount": "10",
}

def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')

def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    query = parsed_url.query  # Include the query part
    fragment = parsed_url.fragment  # Include the fragment part

    normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
    return normalized_url


def aggressive_url_norm(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url

def parse_accessibility_tree(node, depth=0):
    if not node or 'role' not in node:
        return ""

    indent = "\t" * depth
    role = node.get('role', '')
    name = node.get('name', '')
    node_str = f"{indent}[{role}] {repr(name)}"

    node_str += "\n"

    # Recursively process children
    for child in node.get('children', []):
        child_str = parse_accessibility_tree(child, depth + 1)
        node_str += child_str

    return node_str

async def extract_interaction_info(html): #use general input type
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

async def get_usable_elements(page, leaf): # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean(interactable_elements, leaf)
    cleaned_and_reduced_elements = await reduce_duplicate_elements(cleaned_elements, leaf)
    # print("CLEANED AND REDUCED")
    # print(cleaned_and_reduced_elements)
    return cleaned_and_reduced_elements

async def parse_and_clean(elements, parent_node):
    global all_htmls
    cleaned_output = []
    for element in elements:
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")

        # print(f"HREF: {href}")

        if not await element.is_visible() or await element.is_hidden():
            continue
        if await element.is_disabled():
            continue
        if "disabled=\"disabled\"" in html:
            continue

        if href and href.startswith('#'):
            continue
        elif href is not None and (normalize_url(href) in all_links or (url_depth(normalize_url(href)) <= 1 and href.endswith(".html"))):
            print(f"REMOVED href: {href}")
            continue


        # print(f"HREF: {href}")
        if parent_node.parent and href and parent_node.parent.url == normalize_url(href): # TODO WHAT?
            continue

        if "type='hidden'" in html or 'type="hidden"' in html:
            continue
        # How does query selector know siblings????
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


        interaction_info = await extract_interaction_info(html)


        element_info = (xpath, interaction_info, html)
        cleaned_output.append(element_info)
        all_htmls.append(html)
        # # print(f"USED html: {html}")
        # # print(f"xpath: {xpath}")

    return cleaned_output

async def step_by_xpath(page, edge):
    # edge_info = (interaction_info, generated_text, html, xpath)
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

async def interact_element_by_xpath(page, xpath, interaction_info, html, node):
    global user_context
    await page.wait_for_load_state('networkidle')
    await page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            links.forEach(link => {
                link.target = '_self';
            });
        }''')
    locator = page.locator(f'xpath={xpath}')
    print("LOCATED! ")
    print(f"HTML: {html}")
    count = await locator.count()
    print(f"BEFORE URL: {page.url}")
    # print("INTERACTING")
    # print(f"Interaction info: {interaction_info}")
    # print(html)

    if count == 0:
        print(f"No elements found with this xpath: {xpath}")
        return
    elif count == 1:
        print('One element found with this xpath')
    else:
        print('Multiple elements found with this xpath')


    if await locator.is_disabled() or await locator.is_hidden():
        print("For some reason disabled")

    before_tree = node.acc_tree
    visible_text = get_visible_from_html(html)
    url1 = copy.deepcopy(page.url)

    if interaction_info == "input":
        # # print(f"Trying to input text")
        # return
        generated_text = use_gpt_fill_input(before_tree, html, user_context) # maybe needs xpath? idk
        # generated_text = "TESTING MODE"
        # # print(f"Generated text: {generated_text}")
        await page.wait_for_load_state('networkidle')
        await locator.first.fill(generated_text)
        await page.wait_for_load_state('networkidle')
        # if 'search' in html: ????
        await page.keyboard.press('Enter')
        await page.wait_for_load_state('networkidle')

        action_description = f"Entered {generated_text} into {html} and pressed enter"



        # TODO
        edge_info = (interaction_info, generated_text, html, xpath, visible_text)


    elif interaction_info in ["link", "button", "checkbox"]:
        # print(f"BEFORE ADDRESS {page.url}")
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        await page.keyboard.press('Enter')
        await page.wait_for_load_state('networkidle')
        action_description = f"Clicked on {html}"
        # print(f"AFTER ADDRESS {page.url}")

        # TODO
        edge_info = (interaction_info, interaction_info, html, xpath, visible_text)


    else:
        # print("No specific interaction defined for this element type.")
        return

    await page.wait_for_load_state('networkidle')
    print(f"interaction info: {interaction_info}\n html: {html}")
    after_tree = parse_accessibility_tree(await page.accessibility.snapshot())
    url2 = copy.deepcopy(page.url)
    difference = use_gpt_get_difference(before_tree, after_tree, url1, url2, action_description)
    print(f"PAGE URL: {page.url}\n URL2: {url2}")
    child_node = IntrastateWebPageNode(url=page.url, edge=edge_info, private=difference, acc_tree=after_tree)
    print("NEW CHILD BIRTHED! ")
    print(f"BEFORE: {url1}\nAFTER: {url2}")
    # input("TONK")
    # print("NEW CHILD BIRTHED! ")
    # print(child_node)
    node.add_child(child_node)

class IntrastateWebPageNode:
    unique_interacts_visible = set()
    unique_interacts_html = set()
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

    def __str__(self):
        return f'URL: {self.url}'
    '''
        def __str__(self):
        return f'IntrastateWebPageNode(url={self.url}, edge={self.edge}, private={self.private}, ' \
               f'acc_tree={self.acc_tree}, children_count={len(self.children)}, ' \
               f'trajectory={self.trajectory})'

    '''





def use_gpt_fill_input(tree_str, specific_html, user_context):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop. You are tasked with analyzing a web page based on the entire page's accessibility tree and one element's specific HTML."},
        {"role": "system",
         "content": "The HTML will represent an element that you must input some text into."},
        {"role": "system",
         "content": "The accessibility tree will be a string representation of the accessibility tree of the web page."},
        {"role": "system",
         "content": "You will also be given some context about the user, which will be a dictionary of information about the user."},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, use '''N/A''' as the input."},
        {"role": "system",
         "content": "Reason through your answer, then give the exact string you would input into the box enclosed by '''s, like this: \n '''I would input this string'''. Do not include reasoning in your enclosed answer."},
        {"role": "user",
        "content": f"Here's the information, what should be input into the element represented by the specific HTML? \n Specific element HTML: {specific_html}\nCurrent page accessibility tree:\n{tree_str}\nUser context: {user_context}\n"}
    ]

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        # model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0.0,
        max_tokens=400
    )

    result = response.choices[0].message.content

    pattern = r"\'\'\'(.*?)\'\'\'"

    match = re.search(pattern, result, re.DOTALL)
    # # print(f"RESULT: {result}")
    if match:
        final_answer = match.group(1).strip()
        return final_answer
    else:
        return "FAILURE"

    return "FAILURE"



def use_gpt_get_difference(tree_str1, tree_str2, url1, url2, action):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop. You are tasked with telling me what the effect of an action performed on a web page is, given the accessibility trees and url of the web page before and after the action, as well as the html of the element the action was performed on."},
        {"role": "system",
         "content": "Your answers are to be used to tag element interactions, so please be general and concise. You have to give me your description using general object types (like dates, products, numbers.etc), instead of specific instances of these objects (like June 24th, tweezers, 4). Do not ever give any information about amounts or quantities. Do definitely give any general type information, while being general, as long as it doesn't violate the other requirements I've given you. Mention if there's a change in the purpose of the web page."},
        {"role": "system",
         "content": "Do not include any specific details about visual or informational changes to the page, only what these changes imply. Only include these changes if they are necessary to describe the effect of the action. Use the URLs and accessibility trees, if no navigation occured do not mention navigation."},
        {"role": "system",
         "content": "This is important: if there's a difference in ordering of products/orders.etc between two accessibility trees (e.g., one has older orders, or price has become descending), you must include this difference in your answer. "},
        {"role": "system",
         "content": "Carefully and rigorously reason through your answer step by step, then give the exact string you would input into the box enclosed by ''', like this: \n '''This is the difference between these two web page states'''. Do not include reasoning in your enclosed answer."},
        {"role": "system",
         "content": "If you are unsure of your answer, give as your answer '''N/A'''. If no major change occured (e.g., action did nothing and url doesn't change and accessibility tree has no major or structural changes), reply with '''N/A'''. REMEMBER TO BE AS GENERAL AS POSSIBLE, DO NOT INCLUDE SPECIFICS."},
        {"role": "user",
        "content": f"Give me the effect of the action. Accessibility tree before the action: {tree_str1}\nURL before the action: {url1}\n The action: {action}\n Accessibility tree after the action:\n{tree_str2}\nURL after the action: {url2}"}
    ]

    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=messages,
        temperature=0.0,
        max_tokens=400
    )

    result = response.choices[0].message.content

    pattern = r"\'\'\'(.*?)\'\'\'"

    match = re.search(pattern, result, re.DOTALL)
    print(f"RESULT: {result}")
    if match:
        final_answer = match.group(1).strip()
        return final_answer
    else:
        return "FAILURE"

def get_leaves(node):
    if node.children == []:
        return [node]
    else:
        leaves = []
        # print(f"NODE CHILDREN: {node.children}")
        for child in node.children:
            leaves.extend(get_leaves(child))
        return leaves

async def scrape_leaves(root_node):
    async with async_playwright() as p:


        # At root node url, always start at root node url

        leaves = get_leaves(root_node)

        for leaf in leaves:
            if not leaf.url.startswith(aggressive_url_norm(root_node.url)):
                continue
            outer_browser = await p.chromium.launch(headless=False)
            outer_page = await outer_browser.new_page()
            await outer_page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
            await outer_page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
            await outer_page.get_by_label("Password", exact=True).fill('Password.123')
            await outer_page.get_by_role("button", name="Sign In").click()
            await outer_page.goto(root_node.url)

            trajectory = leaf.trajectory

            # print(f"LEAF TRAJ: {leaf.trajectory}")
            '''
            for edge in trajectory: # does nothing for root_node
                print("BEFORE STEP")
                print(outer_page.url)
                await step_by_xpath(outer_page, edge) # FIRST STEP FUCKS UP SOMEHOW
                print("AFTER STEP")
                print(outer_page.url)
            '''

            # TODO RECONSIDER STEPPING STRATEGY FOR EXCLUSIVE ENTRIES, PERHAPS START STATE UPON ENTRY?

            elements = await get_usable_elements(outer_page, leaf)

            # print("GOT ELEMENTS")

            # print(elements)

            # print("CLOSING PAGE")
            if elements == []:
                # print("NO ELEMENTS FOUND")
                return


            # edge_info = (interaction_info, generated_text, html, xpath, visible_text)
            for xpath, interaction_info, html in elements:
                inner_browser = await p.chromium.launch(headless=False)


                # # print("-------------------")
                # # print(f"Interaction info: {interaction_info}")
                # # print(html)
                # # print("-------------------")

                inner_page = await inner_browser.new_page()
                # print("NEW PAGE GOING THROUGH")

                await inner_page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
                await inner_page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
                await inner_page.get_by_label("Password", exact=True).fill('Password.123')
                await inner_page.get_by_role("button", name="Sign In").click()

                await inner_page.goto(root_node.url)

                # print("LOGGED IN")

                trajectory = leaf.trajectory

                # # print(f"LEAF TRAJ: {leaf.trajectory}")

                for edge in trajectory:  # does nothing for root_node
                    await step_by_xpath(inner_page, edge)

                print("HAPPY PLACE")



                await interact_element_by_xpath(inner_page, xpath, interaction_info=interaction_info, html=html, node=leaf)

                print("HAPPT INTERACTED!!! ")
                await inner_page.close()
                await inner_browser.close()

            await outer_page.close()
            await outer_browser.close()


def get_visible_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(strip=True)


async def reduce_duplicate_elements(elements, parent_node): # same url + same visible text = BAD!
    reduced_elements = []

    page_number_remover = re.compile(r'Page\d+')

    for element in elements:
        # Extract text content for comparison
        visible_text = get_visible_from_html(element[2])
        print(f"VISIBLE TEXT: {visible_text}")

        if page_number_remover.search(visible_text):
            continue
        # Use a composite key of xpath, interaction_info, and visible text for uniqueness

        # element_info = (xpath, interaction_info, html)
        # IntrastateWebPageNode.unique_interacts.add((self.url, get_visible_from_html(child.edge[2]), child.edge[0])) (url, vis_text, interaction_info)

        composite_key_visible = (parent_node.url, element[1], visible_text) # should be added later on
        composite_key_html = (parent_node.url, element[1], element[2]) # should catch empty text cases

        if composite_key_visible not in IntrastateWebPageNode.unique_interacts_visible or (composite_key_html not in IntrastateWebPageNode.unique_interacts_html and visible_text.strip() == ''):
            reduced_elements.append(element)
            IntrastateWebPageNode.unique_interacts_visible.add(composite_key_visible)
            IntrastateWebPageNode.unique_interacts_html.add(composite_key_html)

        # print(f"COMPOSITE KEY VISIBLE: {composite_key_visible}")
        # print(f"COMPOSITE KEY HTML: {composite_key_html}")




    return reduced_elements


def serialize_node(node):
    """ Serialize the node and its children into a dictionary. """
    node_data = {
        'url': node.url,
        'edge': node.edge,
        'private': node.private,
        'public': node.public,
        'acc_tree': node.acc_tree,
        'trajectory': node.trajectory,
        'children': [serialize_node(child) for child in node.children]
    }
    return node_data

def save_tree_to_json(root_node, filename):
    with open(filename, 'w') as file:
        json.dump(serialize_node(root_node), file, indent=4)
    print("SAVED TO JSON")


async def main():
    global all_htmls
    async with async_playwright() as p:

        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/tweezers-for-succulents-duo.html"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history/"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/home-kitchen/storage-organization/baskets-bins-containers.html"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/edit/"
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/clothing-shoes-jewelry/women/clothing.html"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/beauty-personal-care/oral-care/orthodontic-supplies.html"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        # def __init__(self, url=None, edge=None, acc_tree=None, embedding=None):
        curr_page_acc_tree = parse_accessibility_tree(await page.accessibility.snapshot())
        # child_node = IntrastateWebPageNode(url=page.url, edge=edge_info, private=difference, acc_tree=after_tree)
        root_node = IntrastateWebPageNode(url=link, edge=None, private=None, acc_tree=curr_page_acc_tree)

        await page.close()
        await browser.close()



    # await scrape_leaves(root_node)

    await scrape_leaves(root_node)


    # save root node
    print("DONE!!!")
    # print_intrastate_node_tree(root_node)
    print(f"ALL HTMLS: {all_htmls}")
    save_tree_to_json(root_node, 'orthosuppliesdraft.json')



        


asyncio.run(main())


