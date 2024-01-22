import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup

async def state_specific_filter(html, xpath, visible_text, flags):
    if flags['section'] == 'shoppingsection':
        if visible_text in ['Add to Cart', 'Add to Wish List', 'Add to Compare'] or 'Review' in visible_text or 'item' in visible_text or 'Page' in visible_text:
            return True
    elif flags['section'] == 'myorders':
        if 'Page' in visible_text or '102050' in visible_text or 'Newsletter' in visible_text or 'Report All Bugs' in visible_text:
            return True
    elif flags['section'] == 'orderpage':
        if'6505551212' in visible_text:
            return True
    return False