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
url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sports-outdoors.html'
page.goto(url)
# set the first page as the current page
page = context.pages[0]
page.bring_to_front()
intent = "buy Image Maryia Men 3D Creative Printed Graphic T Shirts Casual Short Sleeve Crewneck Muscle Tees Personality Realistic Suit"
intent = "go to the next page"
intent = "find me teeth guard"
intent = "click a link"
agent = BaseAgent(intent)
driver = MyDriver(agent,"poopfare", page)
while True:
    next_action = agent.get_next_action(driver.observe_state())
    driver.apply(next_action)
    flag = input("input stop?")
    if flag != "":
        exit()
input("LOOK")