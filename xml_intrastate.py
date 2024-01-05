import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from openai import OpenAI
import os
from bs4 import BeautifulSoup


api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

all_htmls = []

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
    if "<input" in html or "textarea" in html:
        return "input"
    return "Uncased Element"

async def get_usable_elements(page, leaf): # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean(interactable_elements, leaf)
    cleaned_and_reduced_elements = await reduce_duplicate_elements(cleaned_elements, leaf)
    print("CLEANED AND REDUCED")
    print(cleaned_and_reduced_elements)
    return cleaned_and_reduced_elements

async def parse_and_clean(elements, parent_node):
    global all_htmls
    cleaned_output = []
    for element in elements:
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")

        if not await element.is_visible() or await element.is_hidden():
            continue
        if await element.is_disabled():
            continue
        if "disabled=\"disabled\"" in html:
            continue

        if href and href.startswith('#'):
            continue
        elif href is not None and normalize_url(href) in all_links:
            # print(f"USED href: {href}")
            continue

        print(f"HREF: {href}")
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
        # print(f"USED html: {html}")
        # print(f"xpath: {xpath}")

    return cleaned_output

async def step_by_xpath(page, edge):
    # edge_info = (interaction_info, generated_text, html, xpath)
    interaction_info, generated_text, html, xpath = edge
    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')

    count = await locator.count()
    if count == 0:
        print(f"STEPPING: No elements found with this xpath: {xpath}")
        print("IMPOSSIbLE BAD")
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

def print_intrastate_node_tree(node, depth=0):
    if not node:
        return

    # Create an indent based on the depth of the node in the tree
    indent = '    ' * depth

    # Print the current node's details
    print(f"{indent}Node URL: {node.url}")
    print(f"{indent}Edge: {node.edge[2] if node.edge is not None else 'None'}")
    print(f"{indent}Private: {node.private if node.private is not None else 'None'}")
    # acc_tree_preview = (node.acc_tree[:30] + '...') if node.acc_tree else 'None'
    # print(f"{indent}Accessibility Tree: {acc_tree_preview}")
    # print(f"{indent}Number of Children: {len(node.children)}")

    # Recursively print each child node
    for child in node.children:
        print_intrastate_node_tree(child, depth + 1)

async def interact_element_by_xpath(page, xpath, interaction_info, html, node):
    global user_context
    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')
    count = await locator.count()
    print("INTERACTING")
    print(f"Interaction info: {interaction_info}")
    print(html)

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

    if interaction_info == "input":
        # print(f"Trying to input text")
        # return
        generated_text = use_gpt_fill_input(before_tree, html, user_context) # maybe needs xpath? idk
        # print(f"Generated text: {generated_text}")
        await page.wait_for_load_state('networkidle')
        await locator.first.fill(generated_text)
        await page.wait_for_load_state('networkidle')
        # if 'search' in html:
        await page.keyboard.press('Enter')
        await page.wait_for_load_state('networkidle')
        action_description = f"Entered {generated_text} into {html} and pressed enter"

        # TODO
        edge_info = (interaction_info, generated_text, html, xpath)


    elif interaction_info in ["link", "button"]:
        print(f"BEFORE ADDRESS {page.url}")
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        action_description = f"Clicked on {html}"
        print(f"AFTER ADDRESS {page.url}")

        # TODO
        edge_info = (interaction_info, interaction_info, html, xpath)


    else:
        print("No specific interaction defined for this element type.")
        return



    after_tree = parse_accessibility_tree(await page.accessibility.snapshot())
    difference = use_gpt_get_difference(before_tree, after_tree, action_description)
    child_node = IntrastateWebPageNode(url=page.url, edge=edge_info, private=difference, acc_tree=after_tree)
    print("NEW CHILD BIRTHED! ")
    print(child_node)
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
        self.unique_interacts = set()

    def add_child(self, child):
        self.children.append(child)
        child.parent = self
        if self.parent:
            child.trajectory = self.parent.trajectory
        child.trajectory.append(child.edge)

    def __str__(self):
        return f'IntrastateWebPageNode(url={self.url}, edge={self.edge}, private={self.private}, ' \
               f'acc_tree={self.acc_tree}, children_count={len(self.children)}, ' \
               f'trajectory={self.trajectory})'




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
         "content": "If nothing in the user context fits the input box, use \"N/A\""},
        {"role": "system",
         "content": "Reason through your answer, then give the exact string you would input into the box enclosed by '''s, like this: \n '''I would input this string'''"},
        {"role": "user",
        "content": f"Here's the information, what should be input into the element represented by the specific HTML? \n Specific element HTML: {specific_html}\nCurrent page accessibility tree:\n{tree_str}\nUser context: {user_context}\n"}
    ]

    response = client.chat.completions.create(
        # model="gpt-4-1106-preview",
        model="gpt-3.5-turbo-1106",
        messages=messages,
        temperature=0.0,
        max_tokens=400
    )

    result = response.choices[0].message.content

    pattern = r"\'\'\'(.*?)\'\'\'"

    match = re.search(pattern, result, re.DOTALL)
    # print(f"RESULT: {result}")
    if match:
        final_answer = match.group(1).strip()
        return final_answer
    else:
        return "FAILURE"

    return "FAILURE"



def use_gpt_get_difference(tree_str1, tree_str2, action):
    messages = [
        {"role": "system",
         "content": "You are an autonomous agent performing tasks for an user on a webshop. You are tasked with telling me what the effect of an action performed on a web page is, given the accessibility trees of the web page before and after the action, as well as the html of the element the action was performed on."},
        {"role": "system",
         "content": "The accessibility tree will be a string representation of the accessibility tree of the web page."},
        {"role": "system",
         "content": "Your answers are to be used to tag element interactions, so please be general and concise. You have to give me your description using general object types (like dates, products, numbers.etc), instead of specific instances of these objects (like June 24th, tweezers, 4). Do not ever give any information about amounts or quantities. Do definitely give any general type information, while being general, as long as it doesn't violate the other requirements I've given you. Emphasise the effects of the action performed."},
        {"role": "system",
         "content": "Do not include any specific details about visual or informational changes to the page, only what these changes imply. Only include these changes if they are necessary to describe the effect of the action. "},
        {"role": "system",
         "content": "This is important: if there's a difference in ordering of products/orders.etc between two accessibility trees (e.g., one has older orders, or price has become descending), you must include this difference in your answer."},
        {"role": "system",
         "content": "Reason through your answer, then give the exact string you would input into the box enclosed by '''s, like this: \n '''This is the difference between these two web page states'''"},
        {"role": "system",
         "content": "If nothing in the user context fits the input box, return '''N/A''' at the end of your message."},
        {"role": "user",
        "content": f"Give me the effect of the action. Accessibility tree before the action: {tree_str1}\nAccessibility tree before the action:\n{tree_str2}\nThe action: {action}\n"}
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

async def get_leaves(node):
    if node.children == []:
        return [node]
    else:
        leaves = []
        print(f"NODE CHILDREN: {node.children}")
        for child in node.children:
            leaves.extend(await get_leaves(child))
        return leaves

async def scrape_leaves(root_node):
    async with async_playwright() as p:


        # At root node url, always start at root node url

        leaves = await get_leaves(root_node)

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

            for edge in trajectory: # does nothing for root_node
                await step_by_xpath(outer_page, edge)

            print("NOW AT DESIRED PAGE HOPEFULLY")
            print(outer_page.url)
            print(outer_page.url)
            # http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history/
            # http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/catalogsearch/result/?q=Tennis+Balls+24+count

            # Now at leaf state, root starts at root

            elements = await get_usable_elements(outer_page, leaf)

            print("GOT ELEMENTS")

            print(elements)

            print("CLOSING PAGE")
            if elements == []:
                print("NO ELEMENTS FOUND")
                return



            for xpath, interaction_info, html in elements:
                inner_browser = await p.chromium.launch(headless=False)


                # print("-------------------")
                # print(f"Interaction info: {interaction_info}")
                # print(html)
                # print("-------------------")

                inner_page = await inner_browser.new_page()
                print("NEW PAGE GOING THROUGH")

                await inner_page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
                await inner_page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
                await inner_page.get_by_label("Password", exact=True).fill('Password.123')
                await inner_page.get_by_role("button", name="Sign In").click()

                await inner_page.goto(root_node.url)

                print("LOGGED IN")

                trajectory = leaf.trajectory

                # print(f"LEAF TRAJ: {leaf.trajectory}")

                for edge in trajectory:  # does nothing for root_node
                    await step_by_xpath(inner_page, edge)

                print("HAPPY PLACE")



                await interact_element_by_xpath(inner_page, xpath, interaction_info=interaction_info, html=html, node=leaf)

                # tonk = input("Press Enter to continue...")
                # if tonk == '':
                #     pass
                # else:
                #     await browser.close()
                #     break
                await inner_page.close()
                await inner_browser.close()

            await outer_page.close()
            await outer_browser.close()


def get_visible_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(strip=True)


async def reduce_duplicate_elements(elements, parent_node): # same url + same visible text = BAD!
    reduced_elements = []

    for element in elements:
        # Extract text content for comparison
        visible_text = get_visible_from_html(element[2])
        # print(f"VISIBLE TEXT: {visible_text}")
        # Use a composite key of xpath, interaction_info, and visible text for uniqueness

        # element_info = (xpath, interaction_info, html)
        # IntrastateWebPageNode.unique_interacts.add((self.url, get_visible_from_html(child.edge[2]), child.edge[0])) (url, vis_text, interaction_info)

        composite_key_visible = (parent_node.url, element[1], visible_text) # should be added later on
        composite_key_html = (parent_node.url, element[1], element[2]) # should catch empty text cases

        if composite_key_visible not in IntrastateWebPageNode.unique_interacts_visible or (composite_key_html not in IntrastateWebPageNode.unique_interacts_html and visible_text.strip() == ''):
            reduced_elements.append(element)
            IntrastateWebPageNode.unique_interacts_visible.add(composite_key_visible)
            IntrastateWebPageNode.unique_interacts_html.add(composite_key_html)

        print(f"COMPOSITE KEY VISIBLE: {composite_key_visible}")
        print(f"COMPOSITE KEY HTML: {composite_key_html}")




    return reduced_elements


async def main():
    global all_htmls
    async with async_playwright() as p:

        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/tweezers-for-succulents-duo.html"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/"
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history/"
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

    previous_leaf_count = 0
    while True:
        await scrape_leaves(root_node)
        current_leaves = await get_leaves(root_node)
        if len(current_leaves) == previous_leaf_count:
            break
        previous_leaf_count = len(current_leaves)

    '''
    
    elements = await get_usable_elements(page)
    await page.close()
    for xpath, interaction_info, html in elements:

        print("-------------------")
        print(f"Interaction info: {interaction_info}")
        print(html)
        print("-------------------")

        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        await page.goto(link)



        await interact_element_by_xpath(page, xpath, interaction_info=interaction_info, html=html, node=root_node)
        tonk = input("Press Enter to continue...")
        if tonk == '':
            pass
        else:
            await browser.close()
            break
        await page.close()
    '''




    # save root node

    print_intrastate_node_tree(root_node)
    print(f"ALL HTMLS: {all_htmls}")



        


asyncio.run(main())


