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

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password..123')
        await page.get_by_role("button", name="Sign In").click()
        # await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/mofiz-men-s-golf-shirts-short-sleeve-shirts-100-cotton-athletic-shirts-collared-t-shirt-comfortable-polo-shirts.html")
        # page_html = await page.content()
        # # print(page_html)
        # body = extract_product_page(page_html)
        # print(body)
        link = "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/floor-lamps-for-bedrooms-tall-traditional-standing-lamp-with-leaves-design-ambimall-rustic-tall-pole-lamps-for-living-room-office-reading-60-rustic-upright-floor-lights-with-linen-lampshade.html"
        await page.goto(link)
        page_tree = await page.accessibility.snapshot()
        page_tree = parse_accessibility_tree(page_tree)
        print(page_tree)
asyncio.run(main())