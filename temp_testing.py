import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
from impls import *
from drivers import *
import time
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
url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/clothing-shoes-jewelry/men/clothing.html'
page.goto(url)
# set the first page as the current page
page = context.pages[0]
page.bring_to_front()
intent = 'buy a polo shirt'
# intent = "click a link"
agent = BaseAgent(intent)
driver = MyDriver(agent,"poopfare", page)
total_time = 0
while True:
    prev_time = time.time()
    action = driver.observe_state()
    observation_time = time.time() - prev_time
    
    prev_time = time.time()
    next_action = agent.get_next_action(action)
    response_time = time.time() - prev_time
    
    prev_time = time.time()
    driver.apply(next_action)
    apply_time = time.time() - prev_time

    prev_time = time.time()
    if next_action.action_type == Action.Type.CLICK_IMPORTANT:
        try:
            page.wait_for_selector('role=alert', timeout=5000) # Hard coded as fuck
        except:
            pass
        agent.handle_memory(driver.observe_state())
    memory_time = time.time() - prev_time

    print(f"Observation took: {observation_time} seconds")
    print(f"Response took: {response_time} seconds")
    print(f"Action application took: {apply_time} seconds")
    print(f"Memory handling took: {memory_time} seconds")
    total_operations = observation_time + response_time + apply_time + memory_time
    print(f"All operations took: {total_operations} seconds")
    total_time += total_operations
    print(f"Total time: {total_time} seconds")
    flag = input("input stop?")
    prev_time = time.time()
    if flag != "":
        exit()
input("LOOK")