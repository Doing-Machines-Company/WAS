import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
from intrastate_tree import load_intrastate_from_json
from agentprompts import get_interstate, get_intrastate, get_intrastate_type
from interstate_tree import InferenceWebPageNode
from accessibility_tree_utils import parse_accessibility_tree

with open('all_links2.json', 'r') as file:
    all_links = json.load(file)


def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')


def print_intrastate(node, indent=0):
    print(' ' * indent + str(node.edge))
    for child in node.children:
        print_intrastate(child, indent + 4)


def deserialize_interstate(node_data, parent=None):
    # Recreate a InferenceWebPageNode from the dictionary data.
    node = InferenceWebPageNode(
        url=node_data["url"],
        private=node_data["private"],
        public=node_data["public"],
        acc_tree=node_data["acc_tree"],
        embedding=node_data.get("vec_embedding"),
        parent=parent
    )

    for child_data in node_data["children"]:
        child_node = deserialize_interstate(child_data, parent=node)
        node.add_child(child_node)

    return node


def load_interstate_from_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        tree_data = json.load(file)
    return deserialize_interstate(tree_data)


def extract_interaction_info(html):  # use general input type
    if '<a' in html:
        return "link"
    if (
            '<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and (
            "<div" not in html):  # filter out div?
        # or "select" in html DOESN'T HANDLE
        return "button"
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html:
        return "input"
    if "type=\"checkbox\"" in html:
        return "checkbox"
    return "Uncased Element"


def get_visible_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(strip=True)


def extract_info_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    outer_element = soup.find()  # Find the first/outermost tag

    if outer_element:
        info = {
            'tag': outer_element.name,
            'visible_text': outer_element.get_text(strip=True),
            'interaction': extract_interaction_info(str(outer_element)),
            'attributes': outer_element.attrs,
            'raw_html': html  # TODO: Remove this later
        }
        return info
    else:
        return None


def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    query = parsed_url.query  # Include the query part
    fragment = parsed_url.fragment  # Include the fragment part

    normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
    return normalized_url


async def parse_and_clean_new(elements, parent_node):
    cleaned_output = []
    for element in elements:
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")

        if not await element.is_visible() or await element.is_hidden():
            continue
        if await element.is_disabled() or "disabled=\"disabled\"" in html:
            continue
        if href and ((href.startswith('#') and href != '#') or normalize_url(href) in all_links or (
                url_depth(normalize_url(href)) <= 1 and href.endswith(".html"))):
            continue
        if parent_node.parent and href and parent_node.parent.url == normalize_url(href):
            continue
        if "type='hidden'" in html or 'type="hidden"' in html:
            continue

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

        interaction_info = extract_interaction_info(html)
        visible_text = get_visible_from_html(html)

        # Determine if the element is part of a table and capture the row context
        table_context_with_headers = None
        if interaction_info in ["link", "button", "input"]:  # Check if element types usually in tables
            table_context_with_headers = await element.evaluate('''(element) => {
                        let row = element.closest('tr');
                        let headers = [];
                        let dataWithHeaders = {};
                        if (row) {
                            let table = row.closest('table');
                            if (table) {
                                // Get the headers (assuming the headers are in the first row or in <thead>)
                                let headerCells = table.querySelectorAll('thead th') || table.querySelectorAll('tr:first-child th');
                                headerCells.forEach((th, index) => {
                                    headers[index] = th.textContent.trim();
                                });

                                // Get the data in the same row as the element, excluding interactable elements
                                let dataCells = row.querySelectorAll('td');
                                dataCells.forEach((td, index) => {
                                    let clonedCell = td.cloneNode(true);
                                    // Remove interactable elements from the cloned cell
                                    clonedCell.querySelectorAll('a, button, input, select, textarea, [onclick], [role="button"]').forEach(interactable => interactable.remove());
                                    let header = headers[index] || `Column ${index + 1}`;
                                    let cellText = clonedCell.textContent.trim();
                                    if (cellText) {
                                        dataWithHeaders[header] = cellText;
                                    }
                                });
                            }
                        }
                        return dataWithHeaders;
                    }''')
        if table_context_with_headers == dict() or table_context_with_headers == {}:
            table_context_with_headers = None

        element_info = {
            'xpath': xpath,
            'interaction_info': interaction_info,
            'html': html,
            'visible_text': visible_text,
            'table_context': table_context_with_headers
        }
        cleaned_output.append(element_info)

    return cleaned_output


async def get_usable_elements_new(page, leaf):  # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean_new(interactable_elements, leaf)
    return cleaned_elements


def construct_options_from_children(children):
    result = []
    for i in range(len(children)):
        child = children[i]
        result.append(f"{i}) {child.public}\n")
    return result


def get_child_from_index(node, index):
    children = node.children
    return children[index]


def chunk_answers(answers, chunk_size):
    chunked_list = []

    for i in range(0, len(answers), chunk_size):
        chunked_list.append(answers[i:i + chunk_size])

    return chunked_list


def navigate_interstate(start_node, intent, chunk_size=None):
    curr_node = start_node
    for _ in range(10):
        answers = construct_options_from_children(curr_node.children)
        if chunk_size != None:
            chunked_questions = chunk_answers(answers, chunk_size)

            possible_results = []

            for chunk in chunked_questions:
                # print(f"CHUNK: {chunk}")
                # answer = get_interstate(intent, chunk, model_name="gpt-4-1106-preview")
                answer = get_interstate(intent, chunk, model_name="gpt-3.5-turbo-1106")
                if answer != "FAILURE" and answer != "N/A":
                    possible_results.append(answer)

            # print(f"POSSIBLE RESULTS: {possible_results}")
            # (f"curr_node: {curr_node.url}")

            if len(possible_results) == 0:
                return curr_node
            elif len(possible_results) == 1:
                index = int(possible_results[0])
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else:  # Do recursive in future
                possible_nodes = [get_child_from_index(curr_node, int(result)) for result in possible_results]
                filtered_possible_results = construct_options_from_children(possible_nodes)
                # print(f"FILTERED POSSIBLE RESULTS: {filtered_possible_results}")
                answer = get_interstate(intent, filtered_possible_results, model_name="gpt-3.5-turbo-1106")
                if answer != "FAILURE" and answer != "N/A":
                    index = int(answer)
                    child = possible_nodes[index]
                    curr_node = child
                else:
                    break
        else:
            # print(f"POSSIBLES: {answers}")
            answer = get_interstate(intent, answers, model_name="gpt-4-1106-preview")
            # print(f"ANSWER: {answer}")
            if answer != "FAILURE" and answer != "N/A":
                index = int(answer)
                child = get_child_from_index(curr_node, index)
                curr_node = child
            else:
                break
    return curr_node


# interstate_tree = load_interstate_from_file('webpage_MVP_V5.json')
interstate_tree = load_interstate_from_file('webtreeflattened.json')

# intent = "What is the price range of wireless earphone in the One Stop Market?"
# intent = "I want to change my password"
intent = "what is the most recent order i placed in 2022"


# intent = "buy skyr"

# end_state = navigate_interstate(interstate_tree, intent, chunk_size=10)
# end_state = navigate_interstate_bubble(interstate_tree, intent)


def match_edges_with_extracted_info(node, extracted_info):
    matched_edges = []

    for info in extracted_info:
        found = False
        new_info = {
            'visible_text': info['visible_text'],
            # 'interaction': info['interaction'],
            # 'attributes': info['attributes'],
        }

        for i in range(len(node.children)):
            edge = node.children[i].edge
            interaction_info, generated_text, html, xpath, visible_text = edge
            # if visible_text and visible_text == info['visible_text']:
            # if visible_text and info['visible_text'].startswith(visible_text):
            if visible_text and visible_text in info['visible_text']:
                # print("FLAG 1")
                matched_edges.append((new_info, f"ACTION EFFECT: {node.children[i].private}"))
                found = True
                break

        if not found:
            for i in range(len(node.children)):
                edge = node.children[i].edge
                interaction_info, generated_text, html, xpath, visible_text = edge
                if html and html == info['raw_html']:
                    matched_edges.append((new_info, f"ACTION EFFECT: {node.children[i].private}"))
                    found = True
                    break
        if not found: matched_edges.append((new_info, "ACTION EFFECT: UNKNOWN"))

    return matched_edges


def match_unique_actions(node, usable):
    '''

    Returns a tuple of (unique actions, all labelled actions), check length

    '''

    htmls = [item['html'] for item in usable]
    extracted_info = [extract_info_from_html(html) for html in htmls]

    matched_edges = []
    unique_tags = set()

    for info in extracted_info:
        found = False
        new_info = {
            'visible_text': info['visible_text'],
            # 'interaction': info['interaction'],
            # 'attributes': info['attributes'],
        }

        for i in range(len(node.children)):
            edge = node.children[i].edge
            interaction_info, generated_text, html, xpath, visible_text = edge
            # if visible_text and visible_text == info['visible_text']:
            # if visible_text and info['visible_text'].startswith(visible_text):
            if visible_text and visible_text in info['visible_text']:
                # print("FLAG 1")
                matched_edges.append((f"VISIBLE TEXT: {info['visible_text']}", f"ACTION EFFECT: {node.children[i].private}"))
                unique_tags.add((f"VISIBLE TEXT: {info['visible_text']}", f"ACTION EFFECT: {node.children[i].private}"))
                found = True
                break

        if not found:
            for i in range(len(node.children)):
                edge = node.children[i].edge
                interaction_info, generated_text, html, xpath, visible_text = edge
                if html and html == info['raw_html']:
                    if node.children[i].private == "N/A":
                        print("FLAG 2")
                        print(html)
                    if info['visible_text'].strip() == '':
                        matched_edges.append((f"VISIBLE TEXT: UNLABELLED", f"ACTION EFFECT: {node.children[i].private}"))
                        unique_tags.add((f"VISIBLE TEXT: UNLABELLED", f"ACTION EFFECT: {node.children[i].private}"))
                        found = True
                    else:
                        matched_edges.append(
                            (f"VISIBLE TEXT: {info['visible_text']}", f"ACTION EFFECT: {node.children[i].private}"))
                        unique_tags.add(
                            (f"VISIBLE TEXT: {info['visible_text']}", f"ACTION EFFECT: {node.children[i].private}"))
                        found = True
                    break
        if not found:
            if info['visible_text'].strip() == '':
                matched_edges.append((f"VISIBLE TEXT: UNLABELLED", "ACTION EFFECT: UNKNOWN"))
                unique_tags.add((f"VISIBLE TEXT: UNLABELLED", "ACTION EFFECT: UNKNOWN"))
            else:
                matched_edges.append((f"VISIBLE TEXT: {info['visible_text']}", "ACTION EFFECT: UNKNOWN"))
                unique_tags.add((f"VISIBLE TEXT: {info['visible_text']}", "ACTION EFFECT: UNKNOWN"))



    return unique_tags, matched_edges

async def step_by_xpath(page, xpath, interaction_info, html):
    await page.wait_for_load_state('networkidle')
    locator = page.locator(f'xpath={xpath}')

    count = await locator.count()
    if count == 0:
        print(f"STEPPING: No elements found with this xpath: {xpath}")
        return
    elif count == 1:
        print('STEPPING: One element found with this xpath')
    else:
        print('STEPPING: Multiple elements found with this xpath')

    if interaction_info in ['button', 'link', 'checkbox']:
        await page.wait_for_load_state('networkidle')
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
    elif interaction_info == 'input':
        await page.wait_for_load_state('networkidle')

        await locator.first.fill("TESTING MODE")

        await page.wait_for_load_state('networkidle')

        await page.keyboard.press('Enter')

        await page.wait_for_load_state('networkidle')

    else:
        print("FUCK3")


async def do_task(start_node, intent, inter_chunk=10, intra_chunk=None):
    # end_state = navigate_interstate(start_node, intent, inter_chunk=chunk_size)
    # print(f"END URL: {end_state.url}")
    # print(f"END PUBLIC: {end_state.public}")
    # # Assume we are at order history page
    #
    # if "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/edit" in end_state.url: #some are sublinks need better system
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/myaccountedit.json')
    # elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history" in end_state.url:
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/myorders.json')
    # elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/wishlist" in end_state.url:
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/mywishlistNEW.json')
    # elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/address" in end_state.url:
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/myaddressbookNEW.json')
    # elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account" in end_state.url:
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/myaccount.json')
    # elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/newsletter/manage" in end_state.url:
    #     intrastate_tree = load_intrastate_from_json('intrastate_trees/mynewsletter.json')
    # else:
    #     print("OOPS! NO INTRASTATE TREE FOUND")
    #     print(f"END URL: {end_state.url}")
    #     input("PRESS ENTER TO CONTINUE")
    #     exit()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        # await page.goto(end_state.url) # TODO end_state.url
        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history/?p=4")
        intrastate_tree = load_intrastate_from_json('intrastate_trees/myordersNEW.json')

        for _ in range(10):

            # TODO Not as simple, have to match usable actions with intrastate options
            usable = await get_usable_elements_new(page, intrastate_tree)  # element_info = (xpath, interaction_info, html, visible_text)

            '''
            usable elements
            element_info = {
                'xpath': xpath,
                'interaction_info': interaction_info,
                'html': html,
                'visible_text': visible_text,
                'table_context': table_context_with_headers
            }

            '''



            print("EXTRACTED INFO")
            # matched = match_edges_with_extracted_info(intrastate_tree, extracted_info)
            unique, matched = match_unique_actions(intrastate_tree, usable)
            print("MATCHED")
            print(matched)
            print("UNIQUE")
            print(unique)

            seen_action_types = []

            # for i, (info, action_desc) in enumerate(matched):
            #     if action_desc != "ACTION EFFECT: UNKNOWN" and action_desc != "ACTION EFFECT: N/A":  # Unknown is not matched to a private, N/A is private generated didn't know
            #         known_usable.append(usable[i])
            #         combined.append((info, action_desc, f"EXTRA INFO: {usable[i]['table_context']}"))

            for i, (info, action_desc) in enumerate(unique):
                if action_desc != "ACTION EFFECT: UNKNOWN":
                    seen_action_types.append((info, action_desc))

            print("KNOWN USABLE")
            # print(combined)

            # question_for_gpt = [f"{i}) {item}\n" for i, item in enumerate(combined)]
            question_for_gpt = [f"{i}) {item[0]}\n{item[1]}\n" for i, item in enumerate(seen_action_types)]
            print('\n'.join(question_for_gpt))

            answer = get_intrastate_type(intent, '\n'.join(question_for_gpt), model_name="gpt-4-1106-preview")
            # answer = get_intrastate_type(intent, '\n'.join(question_for_gpt), model_name="gpt-3.5-turbo-1106")
            (desired_info, desired_action_desc) = seen_action_types[int(answer)]
            print("BONK")
            print(desired_info)
            print(desired_action_desc)
            print("BONK")

            known_usable = []
            combined = []
            for i, (info, action_desc) in enumerate(matched):
                print(f"INFO: {info}")
                print(f"ACTION DESC: {action_desc}")
                if action_desc == desired_action_desc and info == desired_info:
                    known_usable.append(usable[i])
                    combined.append((info, action_desc, f"EXTRA INFO: {usable[i]['table_context']}"))
            print("TONK!")
            print(known_usable)
            '''
            
            TABLING HERE!
            
            '''
            filtered_question_for_gpt = [f"{i}) {item}\n" for i, item in enumerate(combined)]
            print('\n'.join(filtered_question_for_gpt))

            # answer = get_intrastate(intent, '\n'.join(filtered_question_for_gpt), model_name="gpt-4-1106-preview")
            answer = get_intrastate(intent, '\n'.join(filtered_question_for_gpt), model_name="gpt-3.5-turbo-1106")


            xpath = known_usable[int(answer)]['xpath']
            interaction_info = known_usable[int(answer)]['interaction_info']
            html = known_usable[int(answer)]['html']
            await step_by_xpath(page, xpath, interaction_info, html)

            continue_flag = input("PRESS ENTER TO CONTINUE")
            if continue_flag == '':
                continue
            else:
                exit()

    return None


asyncio.run(do_task(interstate_tree, intent, inter_chunk=10, intra_chunk=None))