import asyncio
from playwright.async_api import async_playwright
from orderpage_extraction import extract_order_page
from productpage_extraction import extract_product_page
import re
import json
import urllib.parse
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
from intrastate_tree import load_intrastate_from_json
from agentprompts import get_interstate, get_intrastate, use_gpt_fill_input, should_search
from interstate_tree import InferenceWebPageNode
from accessibility_tree_utils import parse_accessibility_tree
from navigation_specific_filters import state_specific_filter


async def step_by_xpath(page, xpath, interaction_info):

    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')

    count = await locator.count()
    print(count)
    await locator.first.click()
    input("USE EYES LOOK COUNT")

    if interaction_info == 'link':
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')

    elif interaction_info == 'button':
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        # TODO USE CURRENT URL AND BUTTON HTML
    elif interaction_info == 'checkbox':
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')

    elif interaction_info == 'radio':
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')

    elif interaction_info == 'input':
        await page.wait_for_load_state('networkidle')

        # await locator.first.fill("TESTING MODE")

        specific_html = 'html'
        input_string = "TONK"
        # print(f"INPUT STRING: {input_string}")
        # print(f"HTML: {html}")
        # input("CHECK WITH EYES")
        if "<input id=\"search\"" not in specific_html:
            await locator.first.fill(input_string)

        await page.wait_for_load_state('networkidle')
        if "id(\"search\")" in xpath:
            await page.keyboard.press('Enter')

            await page.wait_for_load_state('networkidle')

    else:
        print("UNASCRIBED ACTION")
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()
        # await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/mofiz-men-s-golf-shirts-short-sleeve-shirts-100-cotton-athletic-shirts-collared-t-shirt-comfortable-polo-shirts.html")
        # page_html = await page.content()
        # # print(page_html)
        # body = extract_product_page(page_html)
        # print(body)
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/floor-lamps-for-bedrooms-tall-traditional-standing-lamp-with-leaves-design-ambimall-rustic-tall-pole-lamps-for-living-room-office-reading-60-rustic-upright-floor-lights-with-linen-lampshade.html"
        await page.goto(link)


        await page.wait_for_load_state('networkidle')
        input("LOOK")

        page_tree = parse_accessibility_tree(await page.accessibility.snapshot())
        print(page_tree)
        await step_by_xpath(page, 'id("Rating_4")', 'radio')
        await page.wait_for_load_state('networkidle')
        input("TNK")

        # print(page_tree)
asyncio.run(main())