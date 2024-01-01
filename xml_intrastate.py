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

async def extract_interaction_info(html):
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
    return "Interactable Element"

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
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")
        if await element.is_disabled() or not await element.is_visible() or await element.is_hidden():
            continue


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


        element_info = (xpath, text_content, name_attribute, interaction_info, element_id)
        cleaned_output.append(element_info)

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
        # await locator.scrollIntoViewIfNeeded()
        tree1 = parse_accessibility_tree(await page.accessibility.snapshot())
        with open('tree1.txt', 'w') as file:
            file.write(tree1)
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        tree2 = parse_accessibility_tree(await page.accessibility.snapshot())
        with open('tree2.txt', 'w') as file:
            file.write(tree2)

        return
    else:
        print("Multiple elements with this xpath")
        # await page.wait_for_load_state('networkidle')
        # await locator.first.hover()
        await page.wait_for_load_state('networkidle')
        # await locator.first.scrollIntoViewIfNeeded()
        tree1 = parse_accessibility_tree(await page.accessibility.snapshot())
        with open('tree1.txt', 'w') as file:
            file.write(tree1)
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        tree2 = parse_accessibility_tree(await page.accessibility.snapshot())
        with open('tree1.txt', 'w') as file:
            file.write(tree2)

        print(locator.count())
        return
    return




def use_gpt_fill_input(page, xpath, text):
    pass


async def main():
    async with async_playwright() as p:

        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/tweezers-for-succulents-duo.html"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        elements = await get_usable_elements(page, link)
        await page.close()
        for xpath, text_content, name_attribute, interaction_info, element_id in elements:

            print("-------------------")
            print(interaction_info)
            print(name_attribute)
            print(text_content)
            print(element_id)
            print("-------------------")


            if interaction_info == "Link (click to navigate)" or interaction_info == "Button (click to interact)":
                page = await browser.new_page()

                await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
                await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
                await page.get_by_label("Password", exact=True).fill('Password.123')
                await page.get_by_role("button", name="Sign In").click()
                await page.goto(link)
                await click_element_by_xpath(page, xpath)
                tonk = input("Press Enter to continue...")
                if tonk == '':
                    pass
                else:
                    await browser.close()
                    break
                await page.close()
            else:
                print("Not a link or button")




        await browser.close()


        '''
        descs = []
        
        for xpath, text_content, interaction_info in elements:
            descs.append(text_content) #better naming
            # Example: Click on the first element
            # if elements.index((xpath, text_content, interaction_info)) == 0:
                # await click_element_by_xpath(page, xpath)
        
        
        print(len(set(descs)))
        print(len(set(right_elements)))
        print(set(descs) - set(right_elements))
        print(set(right_elements) - set(descs))
        
        '''

asyncio.run(main())


