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
np = 0
all_created_nodes = dict()


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

def normalize_url(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url

def trim_url_to_depth(url, depth):
    parsed = urlparse(url)

    path_segments = parsed.path.split('/')
    trimmed_path = '/'.join(path_segments[:depth + 1])

    trimmed_url = urlunparse((parsed.scheme, parsed.netloc, trimmed_path, '', '', ''))
    return trimmed_url
async def is_same_domain(url):
    parsed_url = urlparse(url)
    return (parsed_url.netloc == start_domain or
            parsed_url.netloc == start_domain.replace('www.', '') or
            parsed_url.netloc == 'www.' + start_domain) and \
        parsed_url.scheme in [start_scheme, 'http', 'https']


async def load_few_shot_examples(filename):
    with open(filename, 'r') as file:
        return json.load(file)


class WebPageNode:
    def __init__(self, url=None, private=None, public=None, acc_tree=None, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private if public is None else public
        self.parents = set()
        self.ancestor_urls = set()
        if url is not None:
            self.ancestor_urls.add(url)
        if parent is not None:
            self.parents.add(parent)
        self.acc_tree = acc_tree
        self.children = set()
        if children is not None:
            self.children.update(children)
        self.page_embedding = embedding

    def add_child(self, child_node):
        child_node.parents.add(self)  # Set this node as the parent of the child
        self.children.add(child_node)
        child_node.ancestor_urls.update(self.ancestor_urls)

    def to_dict(self):
        return {
            "url": self.url,
            "private": self.private,
            "public": self.public,
            "acc_tree": self.acc_tree,
            "vec_embedding": self.page_embedding,
            "children": [child.to_dict() for child in self.children]
        }

    def choose_parent(self):
        if len(self.parents) > 0:
            min_parent_depth = min([url_depth(parent.url) for parent in self.parents])
            backup_selected_parent = None
            selected_parent = None
            for parent in self.parents:
                if not backup_selected_parent and url_depth(parent.url) == min_parent_depth:
                    selected_parent = parent

                same_depth_child = trim_url_to_depth(self.url, url_depth(parent.url))

                trimmed_url = parent.url[:-5] if parent.url.endswith('.html') else parent.url
                if trimmed_url == same_depth_child:
                    if selected_parent == None:
                        selected_parent = parent
                    elif url_depth(parent.url) >= url_depth(selected_parent.url):
                        selected_parent = parent

            if selected_parent == None:
                selected_parent = backup_selected_parent

            if selected_parent:
                for parent in self.parents:
                    if parent != selected_parent:
                        parent.children.discard(self)

                self.parents = {selected_parent}


        assert (len(self.parents) <= 1)



    def __eq__(self, other):
        if other is None:
            return False
        return self.url == other.url

    def __hash__(self):
        return hash(self.url)


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
    name = node.get('name', '')
    node_str = f"{indent}[{role}] {repr(name)}"

    node_str += "\n"

    # Recursively process children
    for child in node.get('children', []):
        child_str = parse_accessibility_tree(child, depth + 1)
        node_str += child_str

    return node_str


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

    username = 'emma.lopez@gmail.com'
    password = 'Password.123'

    page = await browser.new_page()

    await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
    await page.get_by_label("Email", exact=True).fill(username)
    await page.get_by_label("Password", exact=True).fill(password)
    await page.get_by_role("button", name="Sign In").click()


    await page.goto(url)

    links = await page.query_selector_all('a')
    valid_links = []
    for link in links:
        href = await link.get_attribute('href')
        if href:
            normalized_href = normalize_url(href)
            if await is_same_domain(normalized_href):
                valid_links.append(normalized_href)

    await page.close()
    return valid_links


async def fetch_accessibility_tree(url, browser):

    username = 'emma.lopez@gmail.com'
    password = 'Password.123'

    page = await browser.new_page()

    await page.goto("http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/customer/account/login/")
    await page.get_by_label("Email", exact=True).fill(username)
    await page.get_by_label("Password", exact=True).fill(password)
    await page.get_by_role("button", name="Sign In").click()

    await page.goto(url)

    accessibility_snapshot = await page.accessibility.snapshot()
    tree_str = parse_accessibility_tree(accessibility_snapshot)
    await page.close()
    return tree_str


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
            if url != other_url and other_url in url and url_depth(url) != url_depth(other_url):
                if url in filtered_urls:
                    filtered_urls.remove(url)

    final_urls = []
    for url in filtered_urls:
        original_url = url + '.html' if original_html_status.get(url + '.html', False) else url
        final_urls.append(original_url)

    return final_urls

async def set_cookies(context, cookies):
    await context.add_cookies(cookies)

async def set_local_storage(page, origin, local_storage_data):
    await page.goto(origin)
    for item in local_storage_data:
        await page.evaluate(f"window.localStorage.setItem('{item['name']}', `{json.dumps(item['value'])}`)")


async def process_node(parent_node, browser):
    global np
    global all_processed_links
    global scrape_queue
    global all_seen_links
    global all_created_nodes
    parent_url = parent_node.url
    print("Processing: " + parent_url)

    links = await fetch_links(parent_url, browser)

    new_links = list((set(links).difference(parent_node.ancestor_urls)))

    naively_removed_products = []

    for link in new_links:
        if not link.endswith('.html'):
            naively_removed_products.append(link)
        else:
            same_depth_child = trim_url_to_depth(link, url_depth(parent_url))

            trimmed_url = parent_url[:-5] if parent_url.endswith('.html') else parent_url

            if trimmed_url == same_depth_child:
            # if parent_url == same_depth_child or parent_url == same_depth_child + '.html' or parent_url + '.html' == same_depth_child:
            # if link.endswith('.html') and link.startswith(trimmed_url):
                naively_removed_products.append(link)


    all_seen_links.update(links)

    filtered_links = await filter_urls_getshort(naively_removed_products)


    for link in filtered_links:
        if link not in all_created_nodes:
            tree_str = await fetch_accessibility_tree(link, browser)
            if link.endswith('.html') and url_depth(link) == 1 and 'SKU' in tree_str:
                print(f"Skipped: {link}")
                continue
            functionality = "tonk"
            child_node = WebPageNode(url=link, private=functionality, acc_tree=tree_str, parent=parent_node, children=None)
            all_created_nodes[link] = child_node
            np += 1
            print(np)
            parent_node.add_child(child_node)
            scrape_queue.append(child_node)
            all_processed_links.add(link)
        else:
            child_node = all_created_nodes[link]
            parent_node.add_child(child_node)

    print(f"SANITY PROCESSED LINKS LENGTH: {len(all_processed_links)}")
    print(f"SANITY SEEN LINKS LENGTH: {len(all_seen_links)}")

def collapse_parents(node):
    node.choose_parent()
    children_copy = list(node.children)  # Create a copy of children for safe iteration
    for child in children_copy:
        collapse_parents(child)

async def main():
    global np
    global start_url
    global scrape_queue
    global all_seen_links
    global all_processed_links
    global all_created_nodes
    global cookies
    global local_storage_data
    global origin
    start_url = normalize_url(start_url)
    all_seen_links.add(start_url)
    all_processed_links.add(start_url)



    async with async_playwright() as p:
        browser = await p.chromium.launch()

        '''
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        set_cookies(context, cookies)
        set_local_storage(page, origin, local_storage_data)
        
        '''

        tree_str = await fetch_accessibility_tree(start_url, browser)
        functionality = "tonk"
        root_node = WebPageNode(url=start_url, private=functionality, acc_tree=tree_str, parent=None, children=None)
        all_created_nodes[start_url] = root_node
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



        await browser.close()

    collapse_parents(root_node)

    with open('missed_links_v11_0.txt', 'w') as file:
        for item in missed_links:
            file.write(item + "\n")

    tree_data = serialize_tree(root_node)
    with open('webpage_tree_v21.json', 'w', encoding='utf-8') as file:
        json.dump(tree_data, file, ensure_ascii=False, indent=4)


#nice
asyncio.run(main())