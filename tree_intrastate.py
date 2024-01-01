import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse

with open('all_links.json', 'r') as file:
    all_links = json.load(file)


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



def find_interactable_elements(node, seen=None):
    if seen is None:
        seen = set()

    if not node:
        return []

    interactable_elements = []

    role = node.get('role', '')
    name = node.get('name', '')

    interactable_roles = ['button', 'checkbox', 'combobox', 'link', 'listbox', 'menuitem', 'menu', 'radiobutton', 'slider', 'spinbutton', 'tab', 'textbox', 'searchbox', 'switch', 'treeitem', 'dialog', 'tooltip', 'gridcell', 'tabpanel', 'scrollbar', 'option', 'menubutton', 'progressbar', 'range', 'separator', 'radiogroup', 'toolbar', 'tree', 'treegrid', 'grid', 'log', 'marquee', 'timer', 'alert', 'alertdialog', 'window', 'banner', 'document', 'article', 'application', 'region', 'group', 'status', 'alertdialog', 'main', 'navigation', 'search', 'form', 'note', 'complementary', 'contentinfo']

    element_tuple = (role, name)
    if role in interactable_roles and element_tuple not in seen:
        interactable_elements.append({'role': role, 'name': name})
        seen.add(element_tuple)

    for child in node.get('children', []):
        interactable_elements.extend(find_interactable_elements(child, seen))

    return interactable_elements




async def get_accessibility_tree(page):
    return await page.accessibility.snapshot()

async def click_interactable_elements(page, element):
    role = element['role'].lower()
    name = element['name']
    selector = None

    if role == 'button':
        selector = f"button:text-is('{name}'), [role='button']:text-is('{name}')"

    elif role == 'link':
        url = await get_link_url(page, name)
        print(url)
        if url is not None and url.startswith('#'):
            print("Skipping link with anchor")
            return

        selector = f"a[href]:text-is('{name}')"

    if selector:
        try:
            await page.click(selector)
            await page.wait_for_load_state('networkidle')
        except Exception as e:
            print(f"Error clicking on element: {e}")


async def get_link_url(page, link_name):
    link_element = await page.query_selector(f"a:has-text('{link_name}')")

    if link_element:
        href = await link_element.get_attribute('href')
        return href
    else:
        print(f"No link found with the name: {link_name}")
        return None



def use_gpt_fill_input(page, xpath, text):
    pass


async def main():
    async with async_playwright() as p:

        # link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/tweezers-for-succulents-duo.html"
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/index/"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()
        await page.goto(link)

        acc_tree = await get_accessibility_tree(page)
        interactable_elements = find_interactable_elements(acc_tree)
        await page.close()


        for element in interactable_elements:
            print(element)
            page = await browser.new_page()
            await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
            await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
            await page.get_by_label("Password", exact=True).fill('Password.123')
            await page.get_by_role("button", name="Sign In").click()
            await page.goto(link)
            print("logged")
            await click_interactable_elements(page, element)
            print("clicked")
            tonk = input("Press Enter to continue...")
            if tonk == '':
                pass
            else:
                await browser.close()
                break
            await page.close()

        await browser.close()




asyncio.run(main())


