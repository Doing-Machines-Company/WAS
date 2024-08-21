# from playwright.sync_api import sync_playwright
# from scrape7 import *

# # Example usage
# def wait_for_load(page, load_time_ms: int = 850):
#     # https://playwright.dev/python/docs/navigations#navigation-events
#     # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
#     page.wait_for_load_state('load')
#     # page.wait_for_load_state('networkidle')
#     page.wait_for_timeout(load_time_ms)  #

# def login(page):
#     # print('LOGGING IN')
#     page.goto('https://www.dominos.com/en/restaurants?type=Delivery')
#     wait_for_load(page)
#     # page.get_by_label("Street Address", exact=False).fill('934 Keeamoku Street')
#     # page.get_by_label("Suite/Apt #", exact=False).fill('')
#     # page.get_by_label("ZIP Code", exact=False).fill('96814')
#     # page.get_by_label("City", exact=False).fill('Honolulu')
#     # page.get_by_label("State", exact=False).select_option('HI')
#     page.get_by_label("Street Address", exact=False).fill('5819 Centre Ave')
#     page.get_by_label("Suite/Apt #", exact=False).fill('Apt 448')
#     page.get_by_label("ZIP Code", exact=False).fill('15206')
#     page.get_by_label("City", exact=False).fill('Pittsburgh')
#     page.get_by_label("State", exact=False).select_option('PA')  # THIS
#     page.get_by_role("button", name="Continue for Delivery").click()
#     wait_for_load(page)
#     page.get_by_role("button", name="Delivery To").click()
#     page.get_by_role("button", name="Change").click()
#     page.get_by_role("button", name="Carryout").click()
#     page.get_by_role("button", name="Continue").click()
#     wait_for_load(page)
#     # page.get_by_role("button", name="Add").first.click()
#     # page.get_by_role("button", name="Close").first.click()
#     wait_for_load(page)

# def get_element(des_page, des_xpath):
#     return des_page.locator(f"xpath={des_xpath}") if des_xpath else None

# def get_xpath_by_outer_html(page, outer_html):
#     # JavaScript function to find the element by outerHTML and generate its XPath
#     js_code = """
#     (outerHTML) => {
#         function getElementXPath(element) {
#             if (element.id !== '') {
#                 return 'id("' + element.id + '")';
#             }
#             if (element === document.body) {
#                 return element.tagName.toLowerCase();
#             }
#             var ix = 0;
#             var siblings = element.parentNode.childNodes;
#             for (var i = 0; i < siblings.length; i++) {
#                 var sibling = siblings[i];
#                 if (sibling === element) {
#                     return getElementXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
#                 }
#                 if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
#                     ix++;
#                 }
#             }
#         }
#         var element = Array.from(document.querySelectorAll('*')).find(el => el.outerHTML === outerHTML);
#         if (element) {
#             return getElementXPath(element);
#         }
#         return null;
#     }
#     """
#     # Evaluate the JavaScript code in the context of the page
#     xpath = page.evaluate(js_code, outer_html)
#     return xpath

# def make_xpath_friendly(des_xpath):
#     if des_xpath:  # if not empty string and not none
#         return des_xpath if '(' in des_xpath.split("/")[0] else f"//{des_xpath}"
#     else:
#         return None

# def click_element_by_outer_html(des_page, outer_html):
#     js_code = """
#     (outerHTML) => {
#         const element = Array.from(document.querySelectorAll('*')).find(el => el.outerHTML === outerHTML);
#         if (element) {
#             element.click();
#             return true;
#         }
#         return false;
#     }
#     """
#     result = des_page.evaluate(js_code, outer_html)
#     if not result:
#         raise Exception("Element with the specified outerHTML not found")


# with sync_playwright() as p:
#     browser = p.chromium.launch(headless=False)
#     context = browser.new_context()
#     page = context.new_page()
#     cdp_session = page.context.new_cdp_session(page)
#     login(page)
#     input('wait')

#     a1 = Action(Action.Type.CLICK_RADIO, xpath='id("Service_Method_Carryout")', html='<input type="radio" name="Service_Method" id="Service_Method_Carryout" value="Carryout" class="js-serviceMethod" data-quid="side-column-carryout" checked="">')
#     a1.set_friendly_xpath(make_xpath_friendly(a1.xpath))
#     a2 = Action(Action.Type.CLICK_LINK, xpath='id("js-checkoutColumns")/div[1]/div[1]/div[2]/div[1]/table[1]/tbody[1]/tr[1]/td[1]/a[1]', html='<a class="order-summary__item-product-image" href="#!/order/variant/1/"> <img src="https://cache.dominos.com/olo/6_136_0/assets/build/market/US/_en/images/img/products/thumbnails/S_PIZZA.jpg" alt="Large (14&quot;) New York Style Pizza"> </a>')
#     a2.set_friendly_xpath(make_xpath_friendly(a2.xpath))
#     traj = [a1, a2]
#     apply_trajectory(page, traj)

#     input('look')


#     # page.evaluate(
#     #     f"() => {{ let e = document.evaluate('id(\"Service_Method_Carryout\")', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
#     # # ax_nodes = get_ax_tree(cdp_session, page)
#     # # cleaned = AxObservation(ax_nodes, page.url)
#     # # # print(ax_nodes)
#     # input('wait more')
#     # print(page.content())
#     # input('wait more u fuck')
#     #
#     # checkout_xpath = get_xpath_by_outer_html(page, '<a class="order-summary__item-product-image" href="#!/order/variant/1/"> <img src="https://cache.dominos.com/olo/6_136_0/assets/build/market/US/_en/images/img/products/thumbnails/S_PIZZA.jpg" alt="Large (14&quot;) New York Style Pizza"> </a>')
#     # input(checkout_xpath)
#     # # click_element_by_outer_html(page, '<input aria-label="Light Robust Inspired Tomato Sauce" type="radio" data-dpz-track-evt-name="Robust Inspired Tomato Sauce Weight: Light Selected" id="Robust Inspired Tomato Sauce-0.5" name="Robust Inspired Tomato Sauce" class="is-visually-hidden segmented-radio__input" value="0.5">')
#     # # input('waittt')
#     # # page.evaluate(
#     # #     f"() => {{ let e = document.evaluate('{checkout_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
#     #
#     # checkout_xpath = make_xpath_friendly(checkout_xpath)
#     # print(checkout_xpath)
#     # # print(element.count())
#     # # element.first.click()
#     # page.evaluate(
#     #     f"() => {{ let e = document.evaluate('{checkout_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
#     #
#     # input('tonk')

#     input('wait again')
#     # cdp_session.detach()
#     # print(cdp_session.is_detached)

#     # Perform your operations here

#     # When you're done, call the function to clean up resources
#     # manage_resources(cdp_session, page, context)

#     browser.close()
# import os

# def add_effect_txt(directory):
#     for root, dirs, files in os.walk(directory):
#         if 'info.txt' in files:
#             effect_file_path = os.path.join(root, 'effect.txt')
#             if not os.path.exists(effect_file_path):
#                 with open(effect_file_path, 'w') as f:
#                     f.write("")
#                 print(f"Created effect.txt in {root}")

# # Usage
# directory_path = 'dominos'
# add_effect_txt(directory_path)

import anthropic
import time
client = anthropic.Anthropic()
start = time.time()

with open('poopoo1.txt', 'r') as f:
    user_prompt = f.read()
with open('prompts/action_decider/action_decider_system.txt', 'r') as f:
    system_prompt = f.read()
response = client.beta.prompt_caching.messages.create(
    model="claude-3-5-sonnet-20240620",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "You, are a web agent tasked with navigating a website to complete a specific task for a user. You will be provided with an accessibility tree, a task to complete, some retrieved context about the website that may be helpful in completing/understanding this specific task, and two types of memory of actions you've taken so far. Your goal is to analyze the current web page, reason about your task and past actions, and choose the most appropriate next action to complete your task."
        },
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[
        {
            "role": "user",
            "content": "HI"
        }
    ]
)
print(response)
print("Took", time.time() - start)