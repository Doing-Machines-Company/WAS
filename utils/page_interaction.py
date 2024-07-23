import time
from models.accessbility import *
from models.states import *
from utils.web_extraction import *
from utils.element_utils.element_interaction import *
import numpy as np
from scrape_llm import use_gpt_fill_input
import cv2
from typing import Optional, List, Any

def wait_for_load(page: PlaywrightPage, load_time_ms: int = 850):
    # https://playwright.dev/python/docs/navigations#navigation-events
    # https://playwright.dev/python/docs/api/class-page#page-wait-for-load-state-option-state
    page.wait_for_load_state('load')
    # page.wait_for_load_state('networkidle')
    page.wait_for_timeout(load_time_ms)  # this is very finicky, if you set it to a lower time, you risk getting the actions from the previous page. TODO: fix this race
def get_page_state(page: PlaywrightPage, cdpSession: CDPSession, attempts=3) -> PageState:
    result = None

    for _ in range(attempts):
        # Navigate to the given URL and wait for the page to load
        start = time.time()
        wait_for_load(page)
        print("Load took", time.time() - start)
        # Retrieve the accessibility tree and create an AxObservation object
        start = time.time()
        ax_nodes = get_ax_tree(cdpSession)
        print("CDP took", time.time() - start)
        start = time.time()
        cleaned = AxObservation(ax_nodes, page.url)  # LITERALLY THE WHOLE TREE
        print("Cleaning took", time.time() - start)
        #DON'T PRINT FOR NOW, IT'S CLUTTERING EVERYTHING

        # Extract the header and footer HTML
        start = time.time()
        header_html = page.evaluate("document.getElementsByTagName('header')[0]?.outerHTML || ''")
        footer_html = page.evaluate("document.getElementsByTagName('footer')[0]?.outerHTML || ''")
        # header_html = ''
        print("Header footer took", time.time() -start)
        #currently page specific

        # Extract actions from the accessibility nodes and filter out None values, only scrape header and footer on homepage
        # actions = [ax_node_to_action(node, header_html if page.url not in 'https://www.dominos.com/en/' else '', footer_html if page.url not in 'https://www.dominos.com/en/' else '') for node in cleaned.nodes_info]
        '''
        
        IMPORTANT: ACTIONS FROM CLEANED AND NOT RAW AX_NODES!!!
        SO EVERYTHING ACTUALLY IS IN VIEWABLE TREE!!!
        
        '''
        start = time.time()
        indefinite_actions = [ax_node_to_action(node, header_html, footer_html, page.url) for node in cleaned.nodes_info]
        print("Converting to actions took ", time.time() - start)
        new_indefinite_actions = []
        start = time.time()
        for indefinite_action in indefinite_actions:
            if (indefinite_action is not None) and (indefinite_action.action is not None) and (indefinite_action.type_list != []):
                new_indefinite_actions.append(indefinite_action)
        print("Indefinite action loop took", time.time() - start)
        # indefinite_actions = [(tL, a) for (tL, a) in indefinite_actions if tL != []]  # TODO now a list of lists of actions


        # Create and return a PageState object with the normalized URL, HTML content, actions, header HTML, and footer HTML


        result = PageState(
            url=page.url,
            ax_nodes=cleaned.nodes_info,  # note now this nodes info is the cleaned version of nodes that we get out of AxObservation
            html=page.content(),
            actions=new_indefinite_actions,
            header_html=header_html,
            footer_html=footer_html
        )
        if len(result.actions) > 0:
            return result

    return result

def apply_action(page: PlaywrightPage, a: Action, before_screenshot: bytes, playwright_element, found_xpath=None, possible_types=None) -> bool:  # TODO handle multiple possible action types
    for a_type in possible_types:
        try:
            if a_type in [Action.Type.CLICK_LINK, Action.Type.CLICK_IMPORTANT, Action.Type.CLICK_CHECKBOX,
                               Action.Type.CLICK_RADIO, Action.Type.CLICK_GENERAL]:
                if playwright_element.count() > 0:
                    try:
                        page.evaluate(
                            f"() => {{ let e = document.evaluate('{found_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue; e.click(); }}")
                        a.action_type = a_type  # probs not good
                        return True
                    except Exception as e:
                        print(f"Error clicking element via JavaScript click: {e}")

                    try:
                        playwright_element.click(timeout=5000)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error clicking element via Playwright locator.click: {e}")
                try:
                    outer_html_click_success = click_element_by_outer_html(page, a.html)
                    if outer_html_click_success:
                        a.action_type = a_type
                        return True
                except Exception as e:
                    print(f"Error clicking element via OuterHTML {e}")

            elif a_type == Action.Type.SELECT_GENERAL:
                if playwright_element.count() > 0 or found_xpath:
                    try:
                        page.evaluate(f"""
                                (xpath) => {{
                                    const option = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                                    if (option) {{
                                        option.selected = true;
                                        const event = new Event('change', {{ bubbles: true }});
                                        option.parentElement.dispatchEvent(event);
                                    }}
                                }}
                            """, found_xpath)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error selecting element via Javascript: {e}")

                    try:
                        friendly_xpath = remove_last_xpath_item(found_xpath)  # overrides, may be broken after change which makes apply action use playwright objects
                        found_item = page.locator(f"xpath={friendly_xpath}")
                        found_item.select_option(a.desired_option.strip(), timeout=5000)
                    except Exception as e:
                        print(f"Error selecting element via Playwright and trimmed xpath: {e}")

            elif a_type == Action.Type.INPUT:
                if playwright_element.count() > 0:
                    try:
                        input_fill = use_gpt_fill_input('None', before_screenshot, a.html, True)
                        playwright_element.fill(input_fill, force=True, timeout=5000)
                        a.action_type = a_type
                        return True
                    except Exception as e:
                        print(f"Error inputting text into element: {e}")
                else:
                    print("Can't input into nothing")

            elif a_type == Action.Type.GOTO_URL:
                try:
                    page.goto(a.input_string, timeout=5000)
                    # page.wait_for_load_state('networkidle', timeout=5000)
                    a.action_type = a_type
                    return True
                except Exception as e:
                    print(f"Error navigating to URL: {e}")

            elif a_type == Action.Type.GO_BACK:
                pass
                # try:
                #     page.go_back(), timeout=5000
                #     page.wait_for_load_state('networkidle', timeout=5000)
                #     return True, action_type
                # except Exception as e:
                #     print(f"Error going back: {e}")
                page.goto(a.input_string)
                page.wait_for_load_state('networkidle')

        except Exception as e:
            print(f"Unhandled exception for action type {a_type}: {e}")

    return False

def take_screenshot(page, attempts=3, full=False):
    for i in range(attempts):
        try:
            screenshot = page.screenshot(full_page=full)
            return screenshot, True
        except Exception as e:
            print("SCREENSHOT FAILED")
            print(e)
    print("ALL SCREENSHOT ATTEMPTS FAILED")
    # Create a blank image using OpenCV
    height, width = 600, 800  # You can adjust these dimensions as needed
    blank_image = np.zeros((height, width, 3), np.uint8)
    blank_image[:] = (255, 255, 255)  # White background

    # Add text to the image
    font = cv2.FONT_HERSHEY_SIMPLEX
    text = "Screenshot Failed"
    textsize = cv2.getTextSize(text, font, 1, 2)[0]
    text_x = (width - textsize[0]) // 2
    text_y = (height + textsize[1]) // 2
    cv2.putText(blank_image, text, (text_x, text_y), font, 1, (0, 0, 0), 2)

    # Convert the OpenCV image to bytes (similar to Playwright's screenshot output)
    _, buffer = cv2.imencode('.png', blank_image)
    print("SAVING DUMMY SCREENSHOT")
    return buffer.tobytes(), False
