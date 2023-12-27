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


all_seen_links = set()
compress_labels = {}
current_compressed_label = 0
scrape_queue = []
CONCURRENT_BROWSERS = 30
BATCH_SIZE = 10
np = 0

all_nodes = []

# start_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770'
start_url = 'https://www.jchencxh.com/'
parsed_start_url = urlparse(start_url)
start_domain = parsed_start_url.netloc
start_scheme = parsed_start_url.scheme



async def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    if not netloc.startswith('www.'):
        netloc = 'www.' + netloc
    normalized_url = urlunparse((scheme, netloc, parsed_url.path, parsed_url.params, parsed_url.query, parsed_url.fragment))
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

async def interpret_functionality(tree_str):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system",
             "content": "You are an autonomous intelligent agent tasked with analyzing web pages in-depth. Your primary task is to provide a brief and exhaustive evaluation of the web page's overall purpose, without considering the purpose of outgoing links."},
            {"role": "system",
             "content": "You will be given a page's accessibility tree. This is a simplified representation of the webpage, providing key information."},
            {"role": "system",
             "content": "You are to provide very brief and concise descriptions of all functionalities of a web page. Do not include any details about what the web page links to. Do not include any details about links, or what those links may do. Only describe what can be done on the page without going to another link."},
            {"role": "system",
             "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "user",
             "content": "Accessibility Tree Example 1:\n[Accessibility tree details...]\nWhat can be done on this page:\n['Functionality 1', 'Functionality 2']"},
            {"role": "user",
             "content": "Accessibility Tree Example 2:\n[Accessibility tree details...]\nWhat can be done on this page:\n['Functionality A', 'Functionality B']"},
            {"role": "user",
             "content": f"Describe what can be done on this web page based on this accessibility tree:\n{tree_str}\nDo not include any information about what it links to, only what can be done on this page. Provide an exhaustive list of functionalities, keeping descriptions brief."}
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
    def __init__(self, url, private, acc_tree, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private
        self.parent = parent
        self.acc_tree = acc_tree
        self.children = children if children is not None else []


    def add_child(self, child_node):
        child_node.parent = self  # Set this node as the parent of the child
        self.children.append(child_node)

    def backpropagate_public(self, public):
        if self.children == []:
            self.public = self.private
        else:
            descriptions = []
            for child in self.children:
                descriptions.extend(child.public)

    def traverse_up(self):
        # Method to traverse upwards (towards the root)
        node = self
        while node:
            yield node
            node = node.parent

    def traverse_down(self):
        # Method to traverse downwards (towards the leaves)
        nodes = [self]
        while nodes:
            current_node = nodes.pop()
            yield current_node
            nodes.extend(current_node.children)

    def __str__(self):
        parent_url = self.parent.url if self.parent else 'None'
        children_urls = ', '.join([child.url for child in self.children])
        return (f"WebPageNode(URL: {self.url}, Private: {self.private}, "
                f"Public: {self.public}, Parent URL: {parent_url}, "
                f"Children URLs: [{children_urls}]")


def get_compressed_label(role): # Not really good for tokenization, produces more tokens for embedding
    global current_compressed_label
    if role not in compress_labels:
        compress_labels[role] = current_compressed_label
        current_compressed_label += 1
    return compress_labels[role]


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


def clean_accessibility_tree(tree_str: str) -> str:  # Further cleaning perhaps good later on
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


async def process_node(node, browser):
    global np
    global all_seen_links
    global scrape_queue
    url = node.url
    links = await fetch_links(url, browser)
    new_links = list(set(links).difference(all_seen_links))
    all_seen_links.update(new_links)

    for link in new_links:
        tree_str, _ = await fetch_accessibility_tree(link, browser)
        functionality = await interpret_functionality(tree_str)
        # functionality = "tonk"
        child_node = WebPageNode(url=link, private=functionality, acc_tree=tree_str, parent=node, children=None)
        all_nodes.append(child_node)
        np += 1
        print(np)
        node.add_child(child_node)
        scrape_queue.append(child_node)


async def process_batch(batch, browser):
    tasks = [asyncio.create_task(process_node(node, browser)) for node in batch]
    await asyncio.gather(*tasks)


async def do_scrape_bfs():
    global scrape_queue
    async with async_playwright() as p:
        browsers = [await p.chromium.launch() for _ in range(CONCURRENT_BROWSERS)]
        try:
            while scrape_queue:
                for browser in browsers:
                    if scrape_queue:
                        batch = [scrape_queue.pop(0) for _ in range(min(BATCH_SIZE, len(scrape_queue)))]
                        await process_batch(batch, browser)
        finally:
            for browser in browsers:
                await browser.close()


async def main():
    global np
    global start_url
    start_url = await normalize_url(start_url)


    async with async_playwright() as p:
        browser = await p.chromium.launch()
        tree_str, _ = await fetch_accessibility_tree(start_url, browser)
        functionality = await interpret_functionality(tree_str)
        # functionality = "tonk"
        '''
                add first one to tree
                def __init__(self, url, private, acc_tree, parent=None, children=None):
        '''
        root_node = WebPageNode(url=start_url, private=functionality, acc_tree=tree_str, parent=None, children=None)
        np += 1
        all_nodes.append(root_node)
        scrape_queue.append(root_node)
        await browser.close()

    all_seen_links.add(start_url)
    await do_scrape_bfs()
    for node in all_nodes:
        print(node)


asyncio.run(main())