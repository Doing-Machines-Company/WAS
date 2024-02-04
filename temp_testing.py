import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
from impls import *
from drivers import *

#temporary setup
context_manager = sync_playwright()
playwright = context_manager.__enter__()
browser = playwright.chromium.launch(
headless=False)
context = browser.new_context()
page = context.new_page()
client = page.context.new_cdp_session(page)  # talk to chrome devtools
client.send("Accessibility.enable")
page.client = client
page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
page.get_by_label("Password", exact=True).fill('Password.123')
page.get_by_role("button", name="Sign In").click()
url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sports-outdoors.html'
url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/towmus-men-polo-shirts-men-s-polo-shirts-short-sleeve-print-casual-patchwork-collared-pocket-polo-shirts-for-men-tees.html'
page.goto(url)
# set the first page as the current page
page = context.pages[0]
page.bring_to_front()
intent = 'buy this polo'
# intent = "click a link"
agent = BaseAgent(intent)
driver = MyDriver(agent,"poopfare", page)
while True:
    next_action = agent.get_next_action(driver.observe_state())
    driver.apply(next_action)
    agent.handle_memory(driver.observe_state())
    flag = input("input stop?")
    if flag != "":
        exit()
input("LOOK")