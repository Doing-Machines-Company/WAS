import asyncio
from playwright.async_api import async_playwright
import re
import json
from urllib.parse import urlparse, urlunparse
import os
from bs4 import BeautifulSoup
import copy


api_key = os.getenv('OPENAI_API_KEY')



def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')


def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    query = parsed_url.query  # Include the query part
    fragment = parsed_url.fragment  # Include the fragment part

    normalized_url = urlunparse((scheme, netloc, path, '', query, fragment))
    return normalized_url


def aggressive_url_norm(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


async def extract_interaction_info(html):  # use general input type
    if '<a' in html:
        return "link"
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "type=\"radio\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and (
            "<div" not in html):  # filter out div?
        # or "select" in html DOESN'T HANDLE
        return "button"
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html and "type=\"radio\"" not in html:
        # print("HTML HERE!")
        return "input"
    if "type=\"checkbox\"" in html:
        return "checkbox"
    return "Uncased Element"


async def is_good_html(html):  # use general input type
    if 'hidden' in html:
        return False
    if '<a' in html:
        return False
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "type=\"radio\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and (
            "<div" not in html):  # filter out div?
        # or "select" in html DOESN'T HANDLE
        return True
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html and "type=\"radio\"" not in html:
        # print("HTML HERE!")
        return True
    if "type=\"checkbox\"" in html:
        return True
    return False
async def get_usable_elements(page):  # maybe remove duplicates if ever needed
    selector = "a, button, input, select, textarea"
    # await page.wait_for_load_state('networkidle')
    interactable_elements = page.locator(selector)
    input("give it a moment")
    # interactable_elements = interactable_elements.element_handles()


    return interactable_elements







class IntrastateWebPageNode:
    unique_interacts_visible = set()
    unique_interacts_html = set()

    def __init__(self, url=None, acc_tree=None,
                 embedding=None, actions = None):  # represented by url and action, action taken at url/state
        self.url = url
        self.acc_tree = acc_tree
        self.page_embedding = embedding
        self.actions = copy.deepcopy(actions)




async def scrape_leaves():
    async with async_playwright() as p:
        inner_browser = await p.chromium.launch(headless=False)

        inner_page = await inner_browser.new_page()
        # for url in ["https://www.amazon.com/CeraVe-Salicylic-Ounce-Fragrance-Exfoliate/dp/B077TWXCQV?pd_rd_w=4Nfcl&content-id=amzn1.sym.80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_p=80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_r=P5SGAK1N1S0YFM9F6Z2V&pd_rd_wg=VSHPH&pd_rd_r=a6092c4d-c5c0-4b92-996c-ca82eb48f8cd&pd_rd_i=B077TWXCQV&psc=1&ref_=pd_bap_d_grid_rp_0_2_i"]:
        # for url in ["https://www.amazon.com/Brita-Standard-Replacement-Pitchers-Dispensers/dp/B00008IHL8?pd_rd_w=vlxeJ&content-id=amzn1.sym.80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_p=80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_r=FPY94C7R438M71B24HG2&pd_rd_wg=HAEGD&pd_rd_r=462b6bc1-aa73-4ab1-bdd3-88172f587bf2&pd_rd_i=B00008IHL8&psc=1&ref_=pd_bap_d_grid_rp_0_7_i"]:
        # for url in ["https://www.amazon.com/Brita-UltraMax-Filtered-Water-Dispenser/dp/B09WBL9HCS/?_encoding=UTF8&pd_rd_w=Y7Xob&content-id=amzn1.sym.3c3990c3-513c-4686-8d92-a42b4095cecb%3Aamzn1.symc.8b620bc3-61d8-46b3-abd9-110539785634&pf_rd_p=3c3990c3-513c-4686-8d92-a42b4095cecb&pf_rd_r=T2FRQ3K67CMRNN08AH2W&pd_rd_wg=7wVqe&pd_rd_r=bba43b30-7293-4d99-8131-b40592574919&ref_=pd_gw_ci_mcx_mr_hp_d"]:
        for url in ["https://www.amazon.com/YND-Button-Jacket-Wedding-Trousers/dp/B095HJSKXD/ref=sr_1_6?dib=eyJ2IjoiMSJ9.ayQdB1U8kgXWn_mAyahDBy_ni9d42IDEpxML__c_oqcxJkx6K2YtwCo2QoQnOc3U2XmmM7lOP4uwsT93agFa5mRLu7UCsoyKGkebupCpD_7U2VQ3kqyicoXyRwQds5FXPEYscqanvQ15HN7eJtDxs2J3pzyAj0s1LaoteY__vY4RwB_E3GkwTpr5fhDROUnOYaGH7m3R0bBBvrhakwRmBesXW9W6Q8bDx96hxIgUECnKoyfJ1r7NvxISBDTH36HspRg8a4m2WVodL3UdjUW60gC5b-CxJDfOjV_zFQ5mXlM.JOY7vdXhxS2JAyRu5kqOMPzVTOiZ014c4l1IWqnaf10&dib_tag=se&keywords=suit&qid=1708928509&sr=8-6"]:
            await inner_page.goto(url)
            input("take a moment")
            actions_list = []


            usables = await get_usable_elements(inner_page)
            # input("take another moment")
            usables_number = await usables.count()
            for i in range(usables_number):
                # href = await element.get_attribute('href')
                # html = await element.evaluate("element => element.outerHTML")
                # html = element.outer_html()
                html = await usables.nth(i).inner_html()
                print(html)
                actions_list.append(str(html))

            with open('al2.json', 'w') as file:
                json.dump({"my_actions": actions_list}, file)

        await inner_page.close()
        await inner_browser.close()
        # exit()


def get_visible_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text(strip=True)


def serialize_node(node):
    """ Serialize the node and its children into a dictionary. """
    node_data = {
        'url': node.url,
        'trajectory': node.actions,
    }
    return node_data


def save_tree_to_json(root_node, filename):
    with open(filename, 'w') as file:
        json.dump(serialize_node(root_node), file, indent=4)
    print("SAVED TO JSON")


async def main():
    await scrape_leaves()

    # save_tree_to_json(root_node, 'toyamazonscrape.json')


asyncio.run(main())

