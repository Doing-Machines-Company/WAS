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

async def get_usable_elements(page, url):
    await page.goto(url)
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    interactable_elements = await page.locator(selector).element_handles()
    # print(len(interactable_elements))
    # print(interactable_elements)
    cleaned_elements = await parse_and_clean(interactable_elements) # NEED TO REMOVE DUPLICATES
    # print(len(cleaned_elements))
    return cleaned_elements

async def parse_and_clean(elements):
    cleaned_output = []
    for element in elements:

        if not await element.is_visible() or await element.is_disabled():
            continue

        href = await element.get_attribute('href')
        if href and href.startswith('#'):
            # print("IGNORED! ANCHOR ")
            # print(href)
            continue
        elif href is not None and normalize_url(href) in all_links:
            # print("IGNORED! ")
            # print(href)
            continue
        elif href is not None:
            print("KEPT!")
            print(href)

        html = await element.evaluate("element => element.outerHTML")



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

        element_info = (xpath, text_content, name_attribute, interaction_info)
        cleaned_output.append(element_info)

    return cleaned_output


async def click_element_by_xpath(page, xpath):
    locator = page.locator(f'xpath={xpath}')
    href = await locator.get_attribute('href')
    # if href and href.startswith('#'):
    #     return
    count = await locator.count()
    # if not await locator.is_visible() or await locator.is_disabled():
    #     print(f"Element with xpath {xpath} is not clickable (either not visible or disabled).")
    #     return
    if count == 0:
        print(f"No elements with this xpath: {xpath}\n This should be impossible\n What????\n")
        return
    elif count == 1:
        await locator.first.click()
        return
    else:
        print("Multiple elements with this xpath")
        await locator.first.click()
        print(locator.count())
        return
    return


async def click_element_by_attribute(page, attribute, value):
    locator = page.locator(f"[{attribute}='{value}']")
    if await locator.count() > 0:
        await locator.first().click()


def use_gpt_fill_input(page, xpath, text):
    pass


async def main():
    async with async_playwright() as p:
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        elements = await get_usable_elements(page, link)
        await page.close()
        # interactable_descs = []
        # (xpath, text_content, name_attribute, interaction_info)
        for xpath, text_content, name_attribute, interaction_info in elements:
            print("-------------------")
            print(interaction_info)
            print(name_attribute)
            print(text_content)
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
                    browser.close()
                    break
                await page.close()
            else:
                print("Not a link or button")




        await browser.close()
        # print(f"Interactable Elements Descriptions: {interactable_descs}")


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


