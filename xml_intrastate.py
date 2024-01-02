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

async def extract_interaction_info_v0(html): #use general input type
    if 'href="' in html:
        return "Link (click to navigate)"
    if '<button' in html or "type='button'" in html or "role='button'" in html:
        return "Button (click to interact)"
    if "type=\"submit\"" in html:
        return "Submit Button (click to submit form)"
    if "onclick=" in html:
        return "Clickable Element (click to trigger action)"
    if "type=\"text\"" in html or "type='email'" in html or "type='password'" in html:
        return "Text Input (enter text)"
    if "<select" in html:
        return "Dropdown Select (choose an option)"
    if "<textarea" in html:
        return "Text Area (enter multiline text)"
    if "type=\"checkbox\"" in html:
        return "Checkbox (select an option)"
    if "type=\"radio\"" in html:
        return "Radio Button (select one option)"
    if "role=\"combobox\"" in html:
        return "Text Input (combobox)"
    if "type=\"text\"" in html and "<input" in html:
        return "Text Input (general)"
    if "type=\"number\"" in html and "<input" in html:
        return "Text Input (number)"
    return "Interactable Element"

async def extract_interaction_info(html): #use general input type
    if '<a' in html:
        return "Link"
    if '<button' in html or "type='button'" in html or "role='button'" in html:
        return "Button"
    if "<input" in html:
        return "Input"
    return "Uncased Element"

async def get_usable_elements(page, url):
    await page.goto(url)
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    interactable_elements = await page.locator(selector).element_handles()
    # print(len(interactable_elements))
    cleaned_elements = await parse_and_clean(interactable_elements) # NEED TO REMOVE DUPLICATES
    # print(len(cleaned_elementps))
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
        text = await element.text_content()
        text_content = text.strip() if text else None
        if text_content is None:
            match_text = re.search(r'>([^<]+)<', html)
            text_content = match_text.group(1).strip() if match_text else None
            if text_content is None:
                match_name = re.search(r'name=["\']([^"\']+)["\']', html)
                text_content = match_name.group(1) if match_name else "No visible text"

        if text_content == "No visible text" or text_content == "":
            continue


        interaction_info = await extract_interaction_info(html)
        name_attribute = await element.get_attribute("name")
        element_id = await element.get_attribute("id")


        element_info = (xpath, text_content, name_attribute, interaction_info, element_id, html)
        cleaned_output.append(element_info)
        print(f"html: {html}")
        print(f"xpath: {xpath}")

    return cleaned_output


async def click_element_by_xpath(page, xpath):
    locator = page.locator(f'xpath={xpath}')

    count = await locator.count()

    if count == 0:
        print(f"No elements with this xpath: {xpath}\n This should be impossible\n What????\n")
        return
    elif count == 1:
        print("One element with this xpath")
        # await page.wait_for_load_state('networkidle')
        # await locator.first.hover()
        await page.wait_for_load_state('networkidle')
        with open('tree1.txt', 'w') as file:
            file.write(parse_accessibility_tree(await page.accessibility.snapshot()))
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        with open('tree2.txt', 'w') as file:
            file.write(parse_accessibility_tree(await page.accessibility.snapshot()))


        return
    else:
        print("Multiple elements with this xpath")
        # await page.wait_for_load_state('networkidle')
        # await locator.first.hover()
        await page.wait_for_load_state('networkidle')
        with open('tree1.txt', 'w') as file:
            file.write(parse_accessibility_tree(await page.accessibility.snapshot()))
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        with open('tree2.txt', 'w') as file:
            file.write(parse_accessibility_tree(await page.accessibility.snapshot()))

        print(locator.count())
        return
    return

async def interact_element_by_xpath(page, xpath, interaction_info, html):
    locator = page.locator(f'xpath={xpath}')
    count = await locator.count()
    print("INTERACTING")
    print(html)

    if count == 0:
        print(f"No elements found with this xpath: {xpath}")
        return

    if not await locator.is_visible():
        print(f"For some reason not visible")

    if await locator.is_disabled():
        print("For some reason disabled")


    if interaction_info in ["Text Input (enter text)", "Text Input (combobox)", "Text Input (general)"]:
        print(f"Skipped text input")
        generated_text = await use_gpt_fill_input(page, html) # maybe needs xpath? idk
        await page.wait_for_load_state('networkidle')
        await locator.first.fill(generated_text)
    elif interaction_info in ["Link (click to navigate)", "Button (click to interact)", "Submit Button (click to submit form)", "Clickable Element (click to trigger action)"]:
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
    else:
        print("No specific interaction defined for this element type.")

    # Add any necessary wait or additional handling after interaction
    await page.wait_for_load_state('networkidle')


class IntrastateWebPageNode:
    def __init__(self, url=None, private=None, public=None, acc_tree=None, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private if public is None else public
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
def use_gpt_fill_input(page, html):
    pass


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
        for xpath, text_content, name_attribute, interaction_info, element_id, html in elements:

            print("-------------------")
            print(interaction_info)
            print(name_attribute)
            print(text_content)
            print(element_id)
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


