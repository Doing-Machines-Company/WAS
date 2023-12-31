import asyncio
from playwright.async_api import async_playwright
import re

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
    interactable_elements = await page.query_locator(selector).element_handles()
    # print(len(interactable_elements))
    # print(interactable_elements)
    cleaned_elements = await parse_and_clean(interactable_elements)
    # print(len(cleaned_elements))
    return cleaned_elements

async def parse_and_clean(elements):
    cleaned_output = []
    for i in range(len(elements)):
        element = elements[i]
        print(type(element))
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
    if await locator.count() == 0:
        print(f"No elements with this xpath: {xpath}\n This should be impossible\n What????")
    elif await locator.count() == 1:
        await locator.first().click()
    else:
        print("Multiple elements with this xpath")
        await locator.first().click()
        print(locator.count())


async def click_element_by_attribute(page, attribute, value):
    locator = page.locator(f"[{attribute}='{value}']")
    if await locator.count() > 0:
        await locator.first().click()


async def main():
    async with async_playwright() as p:
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/v8-energy-healthy-energy-drink-steady-energy-from-black-and-green-tea-pomegranate-blueberry-8-ounce-can-pack-of-24.html"
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        elements = await get_usable_elements(page, link)
        interactable_descs = []
        # (xpath, text_content, name_attribute, interaction_info)
        for xpath, text_content, name_attribute, interaction_info in elements:
            interactable_descs.append(text_content)
            print("BONK")
            print(xpath)
            print("TONK")
            if elements.index((xpath, text_content, name_attribute, interaction_info)) == 2:

                # try:
                    # print("TONK")
                    # print(name_attribute)
                    # await click_element_by_xpath(page, xpath)
                # except:
                    # print("Failed to click element")
                # input("Press Enter to close the browser finally...")
                break


            # await click_element_by_attribute(page, 'name', 'some_name')


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


