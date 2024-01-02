import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from openai import OpenAI
import os

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

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

def normalize_url(url):  # Very aggressive normalization
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
    if '<button' in html or "type='button'" in html or "role='button'" in html or "select" in html or "select" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html:
        return "button"
    if "<input" in html or "textarea" in html:
        return "input"
    return "Uncased Element"

async def get_usable_elements(page, url): # maybe remove duplicates if ever needed
    await page.goto(url)
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean(interactable_elements)
    return cleaned_elements

async def parse_and_clean(elements):
    cleaned_output = []
    for element in elements:
        if not await element.is_visible() or await element.is_hidden() or await element.is_disabled():
            continue
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")



        if href and href.startswith('#'):
            continue
        elif href is not None and normalize_url(href) in all_links:
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
        print(f"html: {html}")
        print(f"xpath: {xpath}")

    return cleaned_output



async def interact_element_by_xpath(page, xpath, interaction_info, html):
    global user_context
    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')
    count = await locator.count()
    print("INTERACTING")
    print(html)

    if count == 0:
        print(f"No elements found with this xpath: {xpath}")
        return
    elif count == 1:
        print('One element found with this xpath')
    else:
        print('Multiple elements found with this xpath')


    if await locator.is_disabled():
        print("For some reason disabled")

    before_tree = parse_accessibility_tree(await page.accessibility.snapshot())
    print(before_tree)

    if interaction_info == "input":
        print(f"Trying to input text")
        # return
        parse_acc_tree = parse_accessibility_tree(await page.accessibility.snapshot())
        generated_text = use_gpt_fill_input(parse_acc_tree, html, user_context) # maybe needs xpath? idk
        print(f"Generated text: {generated_text}")
        await page.wait_for_load_state('networkidle')
        await locator.first.fill(generated_text)
    elif interaction_info in ["link", "button"]:
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
    else:
        print("No specific interaction defined for this element type.")

    # Add any necessary wait or additional handling after interaction
    await page.wait_for_load_state('networkidle')

    after_tree = parse_accessibility_tree(await page.accessibility.snapshot())
    print(after_tree)


class IntrastateWebPageNode:
    def __init__(self, url=None, private=None, public=None, acc_tree=None, embedding=None, parent=None, children=None): # represented by url and action, action taken at url/state
        self.url = url
        self.private = private # Action taken to reach it and objective accomplished
        self.public = private if public is None else public # Possible objectives of all children
        self.parents = set()
        self.ancestor_urls = set()
        if url is not None:
            self.ancestor_urls.add(url)
        if parent is not None:
            self.parents.add(parent)
        self.acc_tree = acc_tree
        self.children = set()
        if children is not None:
            self.children.update(children)
        self.page_embedding = embedding


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

    return "FAILURE"



def use_gpt_get_difference(tree_str1, tree_str2, action):
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

    return "FAILURE"


async def main():
    async with async_playwright() as p:

        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/tweezers-for-succulents-duo.html"
        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/index"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        elements = await get_usable_elements(page, link)
        await page.close()
        for xpath, interaction_info, html in elements:

            print("-------------------")
            print(interaction_info)
            print("-------------------")

            page = await browser.new_page()

            await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
            await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
            await page.get_by_label("Password", exact=True).fill('Password.123')
            await page.get_by_role("button", name="Sign In").click()
            await page.goto(link)
            await interact_element_by_xpath(page, xpath, interaction_info=interaction_info, html=html)
            tonk = input("Press Enter to continue...")
            if tonk == '':
                pass
            else:
                await browser.close()
                break
            await page.close()




        await browser.close()

        


asyncio.run(main())


