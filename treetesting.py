import asyncio
from playwright.async_api import async_playwright
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
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()
        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/wzqwzj-summer-beach-swimming-upstream-shoes-snorkeling-shoes-tide-shoes-elastic-skin-waterproof-non-slip-diving-shoes-men-and-women-yoga-socks-shoes-outdoor-beach-shoes.html")
        snapshot = await page.accessibility.snapshot()
        print(snapshot['name'])

asyncio.run(main())