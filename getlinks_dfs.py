import asyncio
from typing import List, Dict, Any
from playwright.async_api import async_playwright
import re
from openai import OpenAI
import os

api_key = os.getenv('OPENAI_API_KEY')


client = OpenAI(api_key=api_key)
# from openai.embeddings_utils import get_embedding, cosine_similarity


all_seen_links = set()
compress_labels = {}
current_compressed_label = 0
scrape_queue = []


async def interpret_functionality(tree_str):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system",
             "content": "You are an autonomous intelligent agent tasked with analyzing web pages in-depth. Your primary task is to provide a detailed evaluation of the web page's overall purpose."},
            {"role": "system",
             "content": "You will be given a page's accessibility tree. This is a simplified representation of the webpage, providing key information."},
            {"role": "system",
             "content": "You are to provide very brief and concise descriptions of all functionalities of a web page. Do not include any details about what the web page links to. Do not include any details about links or buttons. Only describe what can be done on the page."},
            {"role": "system",
             "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "user",
             "content": f"Describe what can be done on this web page based on this accessibility tree:\n{tree_str}\nDo not include any information about what it links to, only what can be done on this page. Provide an exhaustive list of functionalities, keeping descriptions brief."}
        ],
        temperature=0.0
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
    def __init__(self, url, private, acc_tree, parent=None, children=None, children_links=None):
        self.url = url
        self.private = private
        self.parent = parent
        self.acc_tree = acc_tree
        self.children = children if children is not None else []
        self.children_links = children_links if children_links is not None else []
        self.public = private

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

        if href and (href.startswith('http') or href.startswith('https')):
            valid_links.append(href)
        else:
            print(f"Invalid link: {href}")

    await page.close()
    return valid_links


async def fetch_accessibility_tree(url, browser):
    page = await browser.new_page()
    await page.goto(url)

    accessibility_snapshot = await page.accessibility.snapshot()
    tree_str, compressed_tree = parse_accessibility_tree(accessibility_snapshot)
    # clean_tree_str = clean_accessibility_tree(tree_str)

    await page.close()
    return tree_str, compressed_tree


async def process_children(links, browser):
    async with async_playwright() as p:
        # print(len(links))
        # print(links)
        # tree_str = await fetch_accessibility_tree(url, browser)
        children_trees = []

        for link in links:
            if link not in all_seen_links:
                try:
                    print(f"Fetching accessibility tree for: {link}")
                    tree_str, compressed_tree = await fetch_accessibility_tree(link, browser)
                    # embedding = openai.Embedding.create(model="text-embedding-ada-002", input=tree_str)
                    '''

                    Compressed tree makes longer embeddings

                    '''
                    # print(cosine_similarity([1.0], [1.0]))
                    # children_trees.append(tree_str)
                    # print(tree_str)
                    # print(await interpret_functionality(tree_str))
                    children_trees.append(tree_str)
                except Exception as e:
                    print(f"Error fetching {link}: {e}")

            print(children_trees)
            print(len(children_trees))

        all_seen_links.union(set(links))
        await browser.close()

async def do_scrape_bfs():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        while scrape_queue:
            parent_node = scrape_queue.pop(0)
            parent_url = parent_node.url

            links = await fetch_links(parent_url, browser)
            new_links = set(links).difference(all_seen_links)

            all_seen_links.update(new_links)
            for link in new_links:
                try:
                    tree_str, compressed_tree = await fetch_accessibility_tree(link, browser)
                    functionality = interpret_functionality(tree_str)
                    grandchildren_links = fetch_links(link, browser)
                    child_node = WebPageNode(url=link, private=functionality, acc_tree=tree_str, parent=parent_node,
                                            children=None, children_links=grandchildren_links)
                    parent_node.add_child(child_node)
                    scrape_queue.append(child_node)
                except Exception as e:
                    print(f"Error fetching {link}: {e}")

        await browser.close()



async def main():
    start_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770'
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        tree_str, _ = await fetch_accessibility_tree(start_url, browser)
        functionality = await interpret_functionality(tree_str)
        children_links = fetch_links(start_url, browser)
        '''
                add first one to tree
                def __init__(self, url, private, acc_tree, parent=None, children=None, children_links=None):
        '''
        root_node = WebPageNode(url=start_url, private=functionality, acc_tree=tree_str, parent=None,
                                children=None, children_links=children_links)
        scrape_queue.append(root_node)
        await browser.close()

    await do_scrape_bfs()
    print(all_seen_links)


asyncio.run(main())
