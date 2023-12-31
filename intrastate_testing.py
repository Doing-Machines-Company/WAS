import asyncio
from playwright.async_api import async_playwright
import re
from openai import OpenAI
import os
from urllib.parse import urlparse, urlunparse
import json

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/v8-energy-healthy-energy-drink-steady-energy-from-black-and-green-tea-pomegranate-blueberry-8-ounce-can-pack-of-24.html"

def get_all_interactables(ax_tree):
    interactables = []
    for line in ax_tree.split("\n"):
        if "button" in line.lower() or "checkbox" in line.lower() or "combobox" in line.lower() or "link" in line.lower() or "radio" in line.lower() or "textbox" in line.lower():
            interactables.append(line)
    return interactables

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


def clean_accessibility_tree(tree_str):  # Further cleaning perhaps good later on
    clean_lines = []
    for line in tree_str.split("\n"):
        if "text" in line.lower():  # Changed from "statictext" to "text"
            prev_lines = clean_lines[-3:]
            match = re.search(r"\[text\] '([^']+)'", line)
            if match:
                text_content = match.group(1)
                if all(text_content not in prev_line for prev_line in prev_lines):
                    clean_lines.append(line)
        else:
            clean_lines.append(line)

    return "\n".join(clean_lines)

async def extract_interaction_info(html):
    if 'href="' in html:
        return "Link (click to navigate)"
    if '<button' in html or "type='button'" in html or "role='button'" in html:
        return "Button (click to interact)"
    if "type='submit'" in html:
        return "Submit Button (click to submit form)"
    if "onclick=" in html:
        return "Clickable Element (click to trigger action)"
    if "type='text'" in html or "type='email'" in html or "type='password'" in html:
        return "Text Input (enter text)"
    if "<select" in html:
        return "Dropdown Select (choose an option)"
    if "<textarea" in html:
        return "Text Area (enter multiline text)"
    if "type='checkbox'" in html:
        return "Checkbox (select an option)"
    if "type='radio'" in html:
        return "Radio Button (select one option)"
    return "Interactable Element"


async def parse_and_clean(elements):
    cleaned_output = []
    for element in elements:
        # Use JavaScript evaluation to get the outer HTML
        html = await element.evaluate("element => element.outerHTML")

        # Skip elements of type 'hidden'
        if "type='hidden'" in html or 'type="hidden"' in html:
            continue

        text = await element.text_content()
        text_content = text.strip() if text else None

        # Check the 'name' attribute in HTML if text_content is None
        if text_content is None:
            # Extract text from HTML content
            match_text = re.search(r'>([^<]+)<', html)
            text_content = match_text.group(1).strip() if match_text else None

            # Extract name from HTML attribute if text_content is still None
            if text_content is None:
                match_name = re.search(r'name=["\']([^"\']+)["\']', html)
                text_content = match_name.group(1) if match_name else "No visible text"


        interaction_info = await extract_interaction_info(html)

        element_info = (text_content, interaction_info)

        cleaned_output.append(element_info)

    return cleaned_output



async def get_clickable_elements(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        username = 'emma.lopez@gmail.com'
        password = 'Password.123'

        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill(username)
        await page.get_by_label("Password", exact=True).fill(password)
        await page.get_by_role("button", name="Sign In").click()
        await page.goto(url)


        selector = "a, button, input[type='button'], input[type='submit'], [onclick], [role='button']"


        clickable_elements = await page.query_selector_all(selector)
        cleaned_elements = await parse_and_clean(clickable_elements)


        await browser.close()
        return cleaned_elements


async def get_usable_elements(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        username = 'emma.lopez@gmail.com'
        password = 'Password.123'

        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.fill("input[name='login[username]']", username)
        await page.fill("input[name='login[password]']", password)
        await page.click("button[type='submit']")
        await page.goto(url)

        selector = "a, button, input, select, textarea, [onclick], [role='button']"

        interactable_elements = await page.query_selector_all(selector)

        cleaned_elements = await parse_and_clean(interactable_elements)

        await browser.close()
        return cleaned_elements

async def fetch_accessibility_tree(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        username = 'emma.lopez@gmail.com'
        password = 'Password.123'

        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill(username)
        await page.get_by_label("Password", exact=True).fill(password)
        await page.get_by_role("button", name="Sign In").click()

        await page.goto(url)

        accessibility_snapshot = await page.accessibility.snapshot()
        tree_str = parse_accessibility_tree(accessibility_snapshot)
        await page.close()

        return tree_str


async def main():
    elements = await get_usable_elements(link)
    print(elements)


asyncio.run(main())