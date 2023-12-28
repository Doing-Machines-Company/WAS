import asyncio
from playwright.async_api import async_playwright
import re
from openai import OpenAI
import os
from urllib.parse import urlparse, urlunparse
import json

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)
# from openai.embeddings_utils import get_embedding, cosine_similarity


all_processed_links = set()
all_seen_links = set()
compress_labels = {}
current_compressed_label = 0
scrape_queue = []
CONCURRENT_BROWSERS = 150
BATCH_SIZE = 5
np = 0


start_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770'
# start_url = 'https://www.jchencxh.com/'
parsed_start_url = urlparse(start_url)
start_domain = parsed_start_url.netloc
start_scheme = parsed_start_url.scheme


def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')

'''
async def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    # if not netloc.startswith('www.'):
    #     netloc = 'www.' + netloc
    normalized_url = urlunparse(
        (scheme, netloc, parsed_url.path, parsed_url.params, parsed_url.query, parsed_url.fragment))
    return normalized_url

'''

async def normalize_url(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


async def is_same_domain(url):
    parsed_url = urlparse(url)
    return (parsed_url.netloc == start_domain or
            parsed_url.netloc == start_domain.replace('www.', '') or
            parsed_url.netloc == 'www.' + start_domain) and \
        parsed_url.scheme in [start_scheme, 'http', 'https']


async def load_few_shot_examples(filename):
    with open(filename, 'r') as file:
        return json.load(file)


def interpret_functionality_TREE(tree_str):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are an autonomous intelligent agent tasked with analyzing web pages in-depth. Your primary task is to provide a detailed evaluation of the web page's overall purpose."},
            {"role": "system",
             "content": "You will be given a page's accessibility tree. This is a simplified representation of the webpage, providing key information."},
            {"role": "system",
             "content": "You are to provide very brief and concise descriptions of all functionalities of a web page. Do not include any details about links or what other links may do or how actions are performed. Only describe what can be done on the page. Be specific about the page's functionality and purpose. Include different functionalities in different descriptions. Do not in any circumstance include navigational details, do not include details about functionality that require navigating to another link or page. Do include page specific details. "},
            {"role": "system",
             "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "user",
             "content": f"Describe what can be done on this web page based on this accessibility tree:\n{tree_str}\nAgain, include only what can be done on this page. Keep descriptions as brief as possible. Keep your entire list as brief as possible."}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content


async def simplify_functionality(fun_str):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {},

        ]
    )


class WebPageNode:
    def __init__(self, url, private, acc_tree, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private
        self.parent = parent
        self.acc_tree = acc_tree
        self.children = children if children is not None else []
        self.page_embedding = embedding

    def add_child(self, child_node):
        child_node.parent = self  # Set this node as the parent of the child
        self.children.append(child_node)

    def to_dict(self):
        return {
            "url": self.url,
            "private": self.private,
            "public": self.public,
            "acc_tree": self.acc_tree,
            "vec_embedding": self.page_embedding,
            "children": [child.to_dict() for child in self.children]
        }


    def __str__(self):
        parent_url = self.parent.url if self.parent else 'None'
        children_urls = ', '.join([child.url for child in self.children])
        return (f"WebPageNode(URL: {self.url}, Private: {self.private}, "
                f"Public: {self.public}, Parent URL: {parent_url}, "
                f"Children URLs: [{children_urls}]")


def get_compressed_label(role):  # Not really good for tokenization, produces more tokens for embedding
    global current_compressed_label
    if role not in compress_labels:
        compress_labels[role] = current_compressed_label
        current_compressed_label += 1
    return compress_labels[role]

def serialize_tree(root_node):
    return root_node.to_dict()


def parse_accessibility_tree(node, depth=0):
    if not node or 'role' not in node:
        return ""

    indent = "\t" * depth
    role = node.get('role', '')
    compressed_role = get_compressed_label(role)  # Get compressed label
    name = node.get('name', '')
    node_str = f"{indent}[{role}] {repr(name)}"
    compressed_node_str = f"{indent}[{compressed_role}] {repr(name)}"

    node_str += "\n"
    compressed_node_str += "\n"

    # Recursively process children
    for child in node.get('children', []):
        child_str, compressed_child_str = parse_accessibility_tree(child, depth + 1)
        node_str += child_str
        compressed_node_str += compressed_child_str

    return node_str, compressed_node_str


def clean_accessibility_tree(tree_str):  # Further cleaning perhaps good later on
    clean_lines = []
    for line in tree_str.split("\n"):
        if "text" in line.lower():  # Changed from "statictext" to "text"
            prev_lines = clean_lines[-3:]
            match = re.search(r"\[text\] '([^']+)'", line)
            if match:
                text_content = match.group(1)
                if all(text_content not in prev_line for prev_line in prev_lines):
                    clean_lines.append(line)
        else:
            clean_lines.append(line)

    return "\n".join(clean_lines)


async def fetch_links(url, browser):
    page = await browser.new_page()
    await page.goto(url)
    links = await page.query_selector_all('a')
    valid_links = []
    for link in links:
        href = await link.get_attribute('href')
        if href:
            normalized_href = await normalize_url(href)
            if await is_same_domain(normalized_href):
                valid_links.append(normalized_href)

    await page.close()
    return valid_links


async def fetch_accessibility_tree(url, browser):
    page = await browser.new_page()
    await page.goto(url)

    accessibility_snapshot = await page.accessibility.snapshot()
    tree_str, compressed_tree = parse_accessibility_tree(accessibility_snapshot)
    await page.close()
    return tree_str, compressed_tree


async def filter_urls_getlong(url_list):
    filtered_urls = []

    for url in url_list:
        is_substring = False
        for other_url in url_list:
            if url != other_url and url in other_url:
                is_substring = True
                break

        if not is_substring:
            filtered_urls.append(url)

    return filtered_urls

async def filter_urls_getshort(url_list):
    original_html_status = {url: url.endswith('.html') for url in url_list}

    modified_urls = [url[:-5] if url.endswith('.html') else url for url in url_list]

    filtered_urls = modified_urls.copy()

    for url in modified_urls:
        for other_url in modified_urls:
            if url != other_url and other_url in url:
                if url in filtered_urls:
                    filtered_urls.remove(url)

    final_urls = []
    for url in filtered_urls:
        original_url = url + '.html' if original_html_status.get(url + '.html', False) else url
        final_urls.append(original_url)

    return final_urls


async def process_node(node, browser):
    global np
    global all_processed_links
    global scrape_queue
    global all_seen_links
    url = node.url
    print("Processing: " + url)
    links = await fetch_links(url, browser)

    new_links = list(set(links).difference(all_processed_links))
    # naively_removed_products = [link for link in new_links if not (url_depth(link) == 1 and link.endswith('.html'))] # This needs to be better
    naively_removed_products = []
    trimmed_url = url[:-5] if url.endswith('.html') else url
    for link in new_links:
        if (link.endswith('.html') and link.startswith(trimmed_url)) or (not link.endswith('.html')):
            naively_removed_products.append(link)

    all_seen_links.update(links)

    filtered_links = await filter_urls_getshort(naively_removed_products)




    for link in filtered_links:
        tree_str, _ = await fetch_accessibility_tree(link, browser)
        if link.endswith('.html') and url_depth(link) == 1 and 'SKU' in tree_str:
            print(f"Skipped: {link}")
            continue
        # functionality = await interpret_functionality(tree_str)
        functionality = "tonk"
        child_node = WebPageNode(url=link, private=functionality, acc_tree=tree_str, parent=node, children=None)
        np += 1
        print(np)
        node.add_child(child_node)
        scrape_queue.append(child_node)
        all_processed_links.add(link)

    print(f"SANITY PROCESSED LINKS LENGTH: {len(all_processed_links)}")
    print(f"SANITY SEEN LINKS LENGTH: {len(all_seen_links)}")

async def main():
    global np
    global start_url
    global scrape_queue
    global all_seen_links
    global all_processed_links
    start_url = await normalize_url(start_url)
    all_seen_links.add(start_url)
    all_processed_links.add(start_url)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        tree_str, _ = await fetch_accessibility_tree(start_url, browser)
        # functionality = await interpret_functionality(tree_str)
        functionality = "tonk"
        root_node = WebPageNode(url=start_url, private=functionality, acc_tree=tree_str, parent=None, children=None)
        np += 1
        print(np)
        scrape_queue.append(root_node)
        while scrape_queue:
            node = scrape_queue.pop(0)
            await process_node(node, browser)
            print(f"Finished Processing: {node.url}")
            print(f"Queue Length: {len(scrape_queue)}")

        print(f"ALL SEEN LINKS LENGTH: {len(all_seen_links)}")
        print(f"ALL PROCESSED LINKS LENGTH: {len(all_processed_links)}")


        missed_links = list(set(all_seen_links).difference(all_processed_links))


        with open('missed_links_v3.txt', 'w') as file:
            for item in missed_links:
                file.write(item + "\n")

        tree_data = serialize_tree(root_node)
        with open('webpage_tree_v2.json', 'w', encoding='utf-8') as file:
            json.dump(tree_data, file, ensure_ascii=False, indent=4)


        await browser.close()


#nice
asyncio.run(main())