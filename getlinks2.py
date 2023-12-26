import asyncio
from typing import List, Dict, Any
from playwright.async_api import async_playwright
import re
import openai

compress_labels = {}
current_compressed_label = 0



def get_compressed_label(role):
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



def clean_accessibility_tree(tree_str: str) -> str: # Further cleaning perhaps good later on
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

async def process_children(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        links = await fetch_links(url, browser)
        # tree_str = await fetch_accessibility_tree(url, browser)
        children_trees = []

        for link in links:
            try:
                print(f"Fetching accessibility tree for: {link}")
                tree_str, compressed_tree = await fetch_accessibility_tree(link, browser)
                embedding = openai.Embedding.create(
                    model="text-embedding-ada-002",
                    input=tree_str
                )
                '''
                
                Compressed tree makes longer embeddings
                
                '''
                print(embedding)
                # children_trees.append(tree_str)
                break
            except Exception as e:
                print(f"Error fetching {link}: {e}")
            break

        await browser.close()
async def main():
    target_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770'  # Replace with your target URL
    await process_children(target_url)


asyncio.run(main())
