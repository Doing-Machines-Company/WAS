import asyncio
from playwright.async_api import async_playwright
import re
import json
import urllib.parse
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
from intrastate_tree import load_intrastate_from_json
from agentprompts import get_interstate, get_intrastate, use_gpt_fill_input, should_search, get_intrastate_full
from interstate_tree import InferenceWebPageNode
from accessibility_tree_utils import parse_accessibility_tree
from navigation_specific_filters import state_specific_filter
from orderpage_extraction import extract_order_page
from productpage_extraction import extract_product_page


def normalize_html(html):
    soup = BeautifulSoup(html, 'html.parser')

    for tag in soup.find_all(attrs={"value": True}):
        tag.attrs['value'] = None  # Remove 'value' attribute

    for tag in soup.find_all(attrs={"checked": True}):
        tag.attrs['checked'] = None  # Remove 'checked' attribute

    for tag in soup.find_all(attrs={"class": True}):
        tag.attrs['class'] = None  # Remove 'checked' attribute

    return str(soup)


with open('all_links2.json', 'r') as file:
    all_links = json.load(file)


def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')


def aggressive_normalize_url(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


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


def extract_interaction_info(html): #use general input type
    if '<a' in html:
        return "link"
    if "type=\"radio\"" in html:
        return "radio"
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and ("<div" not in html): # filter out div?
        # or "select" in html DOESN'T HANDLE
        return "button"
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html:
        return "input"
    if "type=\"checkbox\"" in html:
        return "checkbox"
    return "Uncased Element"


async def find_associated_label(element_html, page):
    if not element_html:
        return ''

    element_soup = BeautifulSoup(element_html, 'html.parser')
    input_element = element_soup.find()
    if not input_element or not input_element.has_attr('id'):
        return ''

    input_id = input_element['id']

    soup = BeautifulSoup(await page.content(), 'html.parser')

    # Find the input element in the main soup

    main_input_element = soup.find(id=input_id)
    if not main_input_element:
        return ''

    # Find the grandparent of the input element in the main soup
    grandparent_div = main_input_element.find_parent().find_parent() if main_input_element.find_parent() else None
    if not grandparent_div:
        return ''

    # Find a label within the grandparent that is associated with the input element
    label = grandparent_div.find('label', {'for': input_id})
    if label:
        span = label.find('span')
        return span.get_text(strip=True) if span else label.get_text(strip=True)

    return ''


async def get_visible_from_html(html, page):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(strip=True)
    if text is None or text.strip() == '':
        label_text = await find_associated_label(html, page)
        if label_text:
            return label_text
        return ''
    return text


async def extract_info_from_html(html, page):
    soup = BeautifulSoup(html, 'html.parser')
    outer_element = soup.find()  # Find the first/outermost tag
    if outer_element:
        info = {
            'tag': outer_element.name,
            'visible_text': await get_visible_from_html(html, page),
            'interaction': extract_interaction_info(html),
            'attributes': outer_element.attrs,
            'raw_html': html # TODO: Remove this later
        }
        return info
    else:
        return None

# def reset_flag(flags):
#     flags = {'state':'None', 'phase': 'navigation_unsearched'}

def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    query = parsed_url.query  # Include the query part
    fragment = parsed_url.fragment  # Include the fragment part


    normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
    return normalized_url


async def parse_and_clean_new(elements, parent_node, page):
    cleaned_output = []
    for element in elements:
        href = await element.get_attribute('href')
        html = await element.evaluate("element => element.outerHTML")


        if not await element.is_visible() or await element.is_hidden():
            continue


        if await element.is_disabled() or "disabled=" in html:
            continue


        if href and ((href.startswith('#') and href != '#') or (aggressive_normalize_url(href) in all_links and aggressive_normalize_url(href) != aggressive_normalize_url(page.url))): # TODO REVEAL PRODUCT TRANSFORMS
            continue
        # if (url_depth(normalize_url(href)) <= 1 and href.endswith(".html")):
            # continue


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
        visible_text = await get_visible_from_html(html, page)

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
                                    let header = headers[index] || `Column ${index}`;
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


async def get_usable_elements_new(page, leaf): # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea, [onclick], [role='button']"
    await page.wait_for_load_state('networkidle')
    interactable_elements = await page.locator(selector).element_handles()
    cleaned_elements = await parse_and_clean_new(interactable_elements, leaf, page)
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


async def navigate_interstate(page, start_node, intent, chunk_size=None):
    # TODO SOMETHING BROKEN HERE
    await page.goto(start_node.url)
    curr_node = start_node
    for _ in range(10):
        answers = construct_options_from_children(curr_node.children)
        if chunk_size != None:
            chunked_questions = chunk_answers(answers, chunk_size)

            possible_results = []

            for chunk in chunked_questions:
                answer = get_interstate(intent, chunk, model_name="gpt-3.5-turbo-1106")
                if answer != "FAILURE" and answer != "N/A" and answer != "FLAG 1":
                    possible_results.append(answer)

            # if flags['phase'] == 'navigation_unsearched':
            #     flags['phase'] = 'intrastate_searched'
            #     possible_results.append("SEARCH") # TODO ADD OPTION HERE TO ALLOW FOR SEARCH OPTION DURING NAVIGATION PHASE

            if len(possible_results) == 0:
                return
            elif len(possible_results) == 1:
                child = get_child_from_index(curr_node, int(possible_results[0]))
                curr_node = child
                await page.goto(curr_node.url)
            else: # Do recursive in future
                # TODO ADD OPTION HERE TO ALLOW FOR SEARCH OPTION DURING NAVIGATION PHASE
                possible_nodes = [get_child_from_index(curr_node, int(result)) for result in possible_results]
                filtered_possible_results = construct_options_from_children(possible_nodes)
                answer = get_interstate(intent, filtered_possible_results, model_name="gpt-3.5-turbo-1106")
                if answer != "FAILURE" and answer != "N/A":
                    index = int(answer)
                    child = possible_nodes[index]
                    curr_node = child
                    await page.goto(curr_node.url)
                    return
                else:
                    return
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
    return


# interstate_tree = load_interstate_from_file('webpage_MVP_V5.json')
interstate_tree = load_interstate_from_file('webtreeflattened.json')


# intent = "find the oldest order"
# intent = "Look at my past orders and find my most recent purchase of a lamp or screen protector, then rate the product with 3 stars, using my nickname GamingEmma?"
# intent = "look at my past orders, and find all food related orders from march 2023"
# intent = "buy TNP Home Theater Speaker Wall Plate Outlet - Speaker Sound Audio Distribution Panel Gold Plated Copper Banana Plug Binding Post Connector Insert Jack Coupler (7.2 Surround)"
# intent = "perform last action"
# intent = "i need a face wash for oily skin"
# intent = "what's in my wishlist?"


async def match_unique_actions(node, usable, page, flags):

    html_list = [item['html'] for item in usable]
    xpaths = [item['xpath'] for item in usable]
    visible_text_list = [await get_visible_from_html(normalize_html(item['html']), page) for item in usable]


    matched_edges = []

    # Manually insert search option


    for j in range(len(usable)):
        found = False

        if await state_specific_filter(html_list[j], xpaths[j], visible_text_list[j], flags):
            continue

        for i in range(len(node.children)):

            interaction_info, generated_text, html, xpath, visible_text = node.children[i].edge

            # if visible_text and visible_text == info['visible_text']:
            # if visible_text and info['visible_text'].startswith(visible_text):

            if visible_text and visible_text in visible_text_list[j]:
                # print("FLAG 1")
                matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: {node.children[i].private}", usable[j]))
                found = True
                break

            if xpath and xpath == xpaths[j]:
                matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: {node.children[i].private}", usable[j]))
                found = True
                break





        if not found:
            for i in range(len(node.children)):
                edge = node.children[i].edge
                interaction_info, generated_text, html, xpath, visible_text = edge
                if html and normalize_html(html) == normalize_html(html_list[j]):
                    if visible_text_list[j].strip() == '':
                        matched_edges.append((f"VISIBLE TEXT: UNLABELLED", f"ACTION EFFECT: {node.children[i].private}", usable[j]))
                        found = True
                    else:
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: {node.children[i].private}", usable[j]))
                        found = True
                    break


        if not found:
            if visible_text_list[j].strip() != '': # TODO CASE ON LINKS
                if flags['section'] == 'shoppingsection':
                    matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Go to page for {visible_text_list[j]}", usable[j]))
                else: # TODO CLEAN UP
                    if usable[j]['interaction_info'] == 'checkbox': # TODO CHOOSE REQUIRED
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", "ACTION EFFECT: Select VISIBLE TEXT option", usable[j]))
                    elif usable[j]['interaction_info'] == 'checkbox' and "required=\"true\"" in html_list[j]:
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Select {visible_text_list[j]} option, REQUIRED TO CHOOSE ONE OF EACH TYPE", usable[j])) # TODO CHANGE TO REQUIRED
                    elif usable[j]['interaction_info'] == 'checkbox':
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", "ACTION EFFECT: Select VISIBLE TEXT option", usable[j]))
                    elif usable[j]['interaction_info'] == 'input' and ("required=\"true\"" in html_list[j] or "required:true" in html_list[j]):
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Input text for {visible_text_list[j]}, INPUT IS REQUIRED", usable[j]))
                    elif usable[j]['interaction_info'] == 'input':
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Input text for {visible_text_list[j]}", usable[j])) # TODO TRIVIAL OPTION SELECTS FOR CHECK BOXES AND RADIO BUTTONS
                    elif usable[j]['interaction_info'] == 'button':
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: CLICK {visible_text_list[j]} BUTTON", usable[j]))
                    elif usable[j]['interaction_info'] == 'radio' and 'required="true"' in html_list[j]:
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Select {visible_text_list[j]} option, REQUIRED TO CHOOSE ONE OF EACH TYPE", usable[j]))
                    elif usable[j]['interaction_info'] == 'radio':
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Select {visible_text_list[j]}", usable[j]))
                    elif usable[j]['interaction_info'] == 'link':
                        matched_edges.append((f"VISIBLE TEXT: {visible_text_list[j]}", f"ACTION EFFECT: Go to page for {visible_text_list[j]}", usable[j]))
            else:
                # print("UNMATCHED")
                # print(usable[j])
                matched_edges.append((f"VISIBLE TEXT: UNLABELLED", "ACTION EFFECT: N/A", usable[j]))

            # else:
            #     print("WHAT THE FUCK")


    return matched_edges

async def step_by_xpath(page, xpath, interaction_info, html, trackers):

    await page.wait_for_load_state('networkidle')


    locator = page.locator(f'xpath={xpath}')

    if interaction_info == 'link':
        await page.wait_for_load_state('networkidle')
        # await page.evaluate(f"""(xpath) => {{
        #             const iterator = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
        #             const element = iterator.iterateNext();
        #             if (element) element.click();
        #         }}""", xpath)
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        trackers[normalize_html(html)] = 'visited' # TODO NEED TO MAKE BETTER, USE HREF???

    elif interaction_info == 'button':
        await page.wait_for_load_state('networkidle')
        # await page.evaluate(f"""(xpath) => {{
        #             const iterator = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
        #             const element = iterator.iterateNext();
        #             if (element) element.click();
        #         }}""", xpath)
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        trackers[normalize_html(html)] = normalize_url(page.url) # TODO MAKE STATE DEPENDENT, E.G., ADD TO CART ONLY PER PRODUCT, BUT NEXT PAGE DEPDENENT ON MENU
        # TODO USE CURRENT URL AND BUTTON HTML
    elif interaction_info == 'checkbox':
        await page.wait_for_load_state('networkidle')
        # await page.evaluate(f"""(xpath) => {{
        #             const iterator = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
        #             const element = iterator.iterateNext();
        #             if (element) element.click();
        #         }}""", xpath)
        await locator.first.click()
        await page.wait_for_load_state('networkidle')
        trackers[normalize_html(html)] = 'pressed'

    elif interaction_info == 'radio':
        await page.wait_for_load_state('networkidle')
        await page.evaluate(f"""(xpath) => {{
            const iterator = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            const element = iterator.iterateNext();
            if (element) element.click();
        }}""", xpath)
        await page.wait_for_load_state('networkidle')
        trackers[normalize_html(html)] = 'pressed'

    elif interaction_info == 'input':
        await page.wait_for_load_state('networkidle')

        tree_str = parse_accessibility_tree(await page.accessibility.snapshot())
        input_string = use_gpt_fill_input(tree_str, html, intent, saved_info)
        if "<input id=\"search\"" not in html:
            if normalize_html(html) not in trackers:
                trackers[normalize_html(html)] = []
            trackers[normalize_html(html)].append(input_string)
        await locator.first.fill(input_string)

        await page.wait_for_load_state('networkidle')
        if "id(\"search\")" in xpath:
            await page.keyboard.press('Enter')

            await page.wait_for_load_state('networkidle')

    else:
        print("UNASCRIBED ACTION")


def convert_to_url_format(input_string):
    formatted_string = input_string.replace(' ', '+')
    return urllib.parse.quote_plus(formatted_string)

def process_trackers(page_url, item, trackers): # THIS IS SO HARD CODED
    norm_html = normalize_html(item['html'])

    interaction_info = item['interaction_info']

    if interaction_info == 'checkbox':
        if norm_html in trackers or "checked=\"checked\"" in item['html']:
            return 'OPTION OF ACTION EFFECT AND VISIBLE TEXT ALREADY ENABLED'
    elif interaction_info == 'radio' and norm_html in trackers:
        return 'RADIO BUTTON ALREADY SELECTED'
    elif interaction_info == 'input' and norm_html in trackers:
        return f"This list of items \'{trackers[norm_html]}\' ALREADY INPUTTED"
    elif interaction_info == 'link' and norm_html in trackers:
        return f"ALREADY VISITED/ATTEMPTED/ENABLED/NAVIGATED TO"
    elif interaction_info == 'button' and norm_html in trackers and trackers[norm_html] == page_url:
        return f"ALREADY ATTEMPTED"
    return ''

async def grab_description(flags, page):
    unparsed_acctree = await page.accessibility.snapshot()
    name = unparsed_acctree['name']
    if flags['section'] == 'shoppingsection':
        print("SHOPPING SECTION")
        return f"Shopping Section for {name}"
    elif flags['section'] == 'accountedit':
        return f"Page titled {name}"
    elif flags['section'] == 'myorders':
        return f"Page titled {name}"
    elif flags['section'] == 'mywishlist':
        return f"Page titled {name}"
    elif flags['section'] == 'myaddressbook':
        return f"Page titled {name}"
    elif flags['section'] == 'myaccount':
        return f"Page titled {name}"
    elif flags['section'] == 'mynewsletter':
        return f"Page titled {name}"
    elif flags['section'] == 'productpage': # TODO ADD INFORMATION RELEVANT
        extracted_product_info = extract_product_page(await page.content())
        return f"Product page for {name}\n{extracted_product_info}"
    elif flags['section'] == 'orderpage': # TODO ADD INFORMATION RELEVANT
        extracted_order_info = extract_order_page(await page.content())
        return f"Order page for {extracted_order_info}"
    else:
        return f"Page titled {name}"


async def do_task(start_node, intent, flags, trackers, inter_chunk=5, intra_chunk=None):


    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
        await page.get_by_label("Email", exact=True).fill('emma.lopez@gmail.com')
        await page.get_by_label("Password", exact=True).fill('Password.123')
        await page.get_by_role("button", name="Sign In").click()

        search_flag = should_search(intent).strip()
        if search_flag == 'YES' and flags['phase'] == 'navigation_unsearched':
            await step_by_xpath(page, 'id(\"search\")', "input", "<input id=\"search\" type=\"text\" name=\"q\" value=\"\" placeholder=\"Search entire store here...\" class=\"input-text\" maxlength=\"128\" role=\"combobox\" aria-haspopup=\"false\" aria-autocomplete=\"both\" autocomplete=\"off\" aria-expanded=\"false\">", trackers)
            flags['phase'] = 'intrastate_searched'
        else:
            await navigate_interstate(page, start_node, intent, chunk_size=inter_chunk)
        # await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/gourmet-kitchn-breyers-classics-ice-cream-variety-pack-homemade-vanilla-breyers-classic-vanilla-chocolate-strawberry-ice-cream-and-chocolate-truffle-9-pack.html")
        # await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/mofiz-men-s-golf-shirts-short-sleeve-shirts-100-cotton-athletic-shirts-collared-t-shirt-comfortable-polo-shirts.html")

        # await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history/")

        for iteration in range(25):
            # page_url = page.url
            # print(page_url)
            # await page.goto(page_url)
            #

            # print(tree_str_new)

            # await page.goto(page.url) # Somehow going to its own URL gets the actuall accessibility tree
            tree_str_new = parse_accessibility_tree(await page.accessibility.snapshot()) # just to get page to refresh/reload so url updates
            tree_str_new = parse_accessibility_tree(await page.accessibility.snapshot())
            # print(tree_str_new)
            # input("USE EYES HERE!")

            if "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/edit" in page.url:  # some are sublinks need better system
                intrastate_tree = load_intrastate_from_json('intrastate_trees/myaccountedit.json')
                flags['section'] = 'accountedit'
            elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sales/order/history" in page.url:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/myorders.json')
                flags['section'] = 'myorders'
            elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/wishlist" in page.url:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/mywishlistNEW.json')
                print("AT WISHLIST SECTION!!!!!!")
                print("OOPS")
                exit()
                flags['section'] = 'mywishlist'
            elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/address" in page.url:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/myaddressbookNEW.json')
                flags['section'] = 'myaddressbook'
            elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account" in page.url:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/myaccount.json')
                flags['section'] = 'myaccount'
            elif "ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/newsletter/manage" in page.url:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/mynewsletter.json')
                flags['section'] = 'mynewsletter'
            elif url_depth(aggressive_normalize_url(page.url)) == 1 and 'SKU' in tree_str_new:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/productpage.json')
                flags['section'] = 'productpage'
            elif "Order #" in tree_str_new and "Order Date" in tree_str_new and "Print Order" in tree_str_new: # TODO SCRAPE SOMETHING
                intrastate_tree = load_intrastate_from_json('intrastate_trees/myaccountedit.json')
                flags['section'] = 'orderpage'
            elif "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/checkout/cart" in page.url: # TODO SCRAPE SOMETHING
                intrastate_tree = load_intrastate_from_json('intrastate_trees/shoppingsection.json')
                flags['section'] = 'shoppingcart'
            elif "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/multishipping/checkout" in page.url: # TODO SCRAPE SOMETHING
                intrastate_tree = load_intrastate_from_json('intrastate_trees/shoppingsection.json')
                flags['section'] = 'shoppingcart'
            elif "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/checkout#shipping" in page.url: # TODO SCRAPE SOMETHING
                intrastate_tree = load_intrastate_from_json('intrastate_trees/shoppingsection.json')
                flags['section'] = 'checkout'
            elif "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/checkout#payment" in page.url: # TODO SCRAPE SOMETHING
                intrastate_tree = load_intrastate_from_json('intrastate_trees/shoppingsection.json')
                flags['section'] = 'checkoutpayment'
            else:
                intrastate_tree = load_intrastate_from_json('intrastate_trees/shoppingsection.json')
                print("AT PRODUCT SECTION!!!!!!")
                flags['section'] = 'shoppingsection'
                # Note this could be view order, I have not cased it on view order pages yet. I should do that.

            # TODO Not as simple, have to match usable actions with intrastate options
            usable = await get_usable_elements_new(page, intrastate_tree) # element_info = (xpath, interaction_info, html, visible_text)



            tables = [item['table_context'] for item in usable]
            page_url = normalize_url(page.url)


            matched = await match_unique_actions(intrastate_tree, usable, page, flags)
            tracked_information = [process_trackers(page_url, item[-1], trackers) for item in matched]
            # print('\n'.join([str('\n'.join([str(i), str(j), str(k)])) for (i, j, k) in matched]))
            # input("LOOK FLAG")
            # TODO WE NEED TO ADD DEFAULT DESCRIPTORS FOR RADIO BUTTONS AND CHECKBOXES
            # TODO INJECT STATE INFORMATION FOR CHECKBOXES, INPUT BOXES.ETC
            # els = [item[-1]['html'] for item in matched]
            # print(els)


            combined = []
            known_usable = []

            for i, (info, action_desc, element) in enumerate(matched):

                if action_desc != "ACTION EFFECT: UNKNOWN" and action_desc != "ACTION EFFECT: N/A": # Unknown is not matched to a private, N/A is private generated didn't know
                    known_usable.append(element)
                    if tables[i] and str(tables[i]).strip() != '' and tracked_information[i] and tracked_information[i].strip() != '':

                        combined.append((info, action_desc, f"EXTRA INFO: {tables[i]}, {tracked_information[i]}")) # TODO HOPEFULLY NO TABLE ITEM NEEDS TRACKERS
                    elif tables[i] and str(tables[i]).strip() != '':

                        combined.append((info, action_desc, f"EXTRA INFO: {tables[i]}"))
                    elif tracked_information[i] and tracked_information[i].strip() != '':

                        combined.append((info, action_desc, f"EXTRA INFO: {tracked_information[i]}"))
                    else:

                        combined.append((info, action_desc))

            if flags['section'] == "orderpage":
                combined.append(('VISIBLE TEXT: Go back to my orders page', 'ACTION EFFECT: Go back to page showing all user orders'))
            elif flags['section'] == "productpage":
                combined.append(('VISIBLE TEXT: Go back to product category/query result page for products', 'ACTION EFFECT: Go back to product category/query result page for products related to current product. '))

            combined.append(('VISIBLE TEXT: Find other site sections or functionality', 'ACTION EFFECT: Discover other site functionality if other options and current page description definitely not relevant to task completion. Use as last resort.'))
            question_for_gpt = [f"{i}) {item}\n" for i, item in enumerate(combined)]
            desc = await grab_description(flags, page)
            (index, retrieved_info) = get_intrastate_full(intent, '\n'.join(question_for_gpt), desc, saved_info, model_name="gpt-4-1106-preview") # TODO ADD TRACKERS FOR ORDERSPAGE.ETC GENERALISE AS MUCH AS POSSIBLE
            # (index, retrieved_info) = get_intrastate_full(intent, '\n'.join(question_for_gpt), desc, saved_info, model_name="gpt-3.5-turbo-1106")
            # TODO GET SUBTASK COMPLETIONS AND RELEVANT INFORMATION FROM ANSWER

            if retrieved_info.strip() != 'N/A':
                saved_info.append(retrieved_info)

            print(f"INDEX: {index}, INFO: {retrieved_info}")
            print(f"ALL MEMORY: {saved_info}")
            if iteration != 0 and index == -1:
                input("STOPPING!")
                exit()

            flags['phase'] = 'intrastate_unsearched'
            # answer = get_intrastate(intent, '\n'.join(question_for_gpt), model_name="gpt-4-turbo-1106")
            if int(index) == len(combined) - 2 and flags['section'] == "orderpage":
                print("GOING BACK TO ORDERS PAGE")
                await page.go_back()
                await page.wait_for_load_state('networkidle')
            elif int(index) == len(combined) - 2 and flags['section'] == "productpage":
                print("GOING BACK TO PRODUCT SECTIONS PAGE")
                await page.go_back()
                await page.wait_for_load_state('networkidle')
            elif int(index) == len(combined) - 1:
                await navigate_interstate(page, start_node, intent, chunk_size=inter_chunk)
                await page.wait_for_load_state('networkidle')
                # await page.goto(end_state.url) # TODO SOMEHOW PREVENT INFINITE STEPPING
                continue
            else:
                xpath = known_usable[int(index)]['xpath']
                interaction_info = known_usable[int(index)]['interaction_info']
                html = known_usable[int(index)]['html']
                await step_by_xpath(page, xpath, interaction_info, html, trackers)
                await page.wait_for_load_state('networkidle')
                # await step_by_attributes(page, attributes, interaction_info, html, trackers)
                # await step_by_html(page, interaction_info, html, trackers)
            # continue_flag = input("PRESS ENTER TO CONTINUE")
            # if continue_flag == '':
            #     continue
            # else:
            #     exit()
        print(saved_info)
    return None

saved_info = []
flags = {'section': 'None', 'phase': 'navigation_unsearched'}  # RESET EVERY NAVIGATION?
trackers = {}
intent = "Look at my past orders and find my most recent purchase of a lamp or screen protector, then rate the product with 3 stars, using my nickname GamingEmma."
intent = "leave a 3 star review for the first lamp you find on the shop, using my nickname GamingEmma"
intent = "find the 45W Super Fast Charger Type C,Samsung Fast Charger for Samsung Galaxy S22 Ultra/S22+/S22/S21 Ultra/S21 Plus/S21/S20/S20 Ultra/Note 20/S10,USB-C Fast Charging Wall Charger with 6.6FT USB C-C Cable Cord with SKU B09FRXSNR2 and leave a review"
# TODO FOR SOME REASON REVIEW BUTTON HIDDEN????
intent = "find the charger section of the website, do not search"


def do_thing(intent):
    asyncio.run(do_task(interstate_tree, intent, flags, trackers, inter_chunk=10, intra_chunk=None))






































# intent = "find me five potato chip options"
intent = "buy me a medium black shiny padded winter coat"
do_thing(intent)