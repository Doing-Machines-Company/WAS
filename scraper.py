from urllib.parse import urlparse, urlunparse
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import os
import json

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

def get_embedding(text, model="text-embedding-ada-002"):
   text = text.replace("\n", " ")
   return client.embeddings.create(input = [text], model=model).data[0].embedding

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
def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


start_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770?#'


def filter_urls(url_list):
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


def filter_shortest_urls(url_list):
    filtered_urls = url_list.copy()

    for url in url_list:
        for other_url in url_list:
            if url != other_url and other_url in url:
                # If the other_url is a substring of url, remove the superstring url
                if url in filtered_urls:
                    filtered_urls.remove(url)
                break

    return filtered_urls

def load_text_file_as_list(file_path):
    with open(file_path, 'r') as file:
        return file.read().splitlines()


def filter_shortest_urls(url_list):
    filtered_urls = url_list.copy()

    while True:
        to_remove = set()

        for url in filtered_urls:
            for other_url in filtered_urls:
                if url != other_url and other_url in url:
                    to_remove.add(url)

        if not to_remove:
            break

        filtered_urls = [url for url in filtered_urls if url not in to_remove]

    return filtered_urls


def filter_urls_getshort(url_list):
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



def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')


ll = load_text_file_as_list('missed_links_v3.txt')

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

def deserialize_node(node_data, parent=None):
    # Recreate a WebPageNode from the dictionary data.
    node = WebPageNode(
        url=node_data["url"],
        private=node_data["private"],
        acc_tree=node_data["acc_tree"],
        embedding=node_data.get("vec_embedding"),
        parent=parent
    )

    for child_data in node_data["children"]:
        child_node = deserialize_node(child_data, parent=node)
        node.add_child(child_node)

    return node

def load_tree_from_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        tree_data = json.load(file)
    return deserialize_node(tree_data)

# Usage example
root_node = load_tree_from_file('webpage_tree_v2.json')
print(len(root_node.children))
t1 = root_node.children[10]
t2 = root_node.children[15]
print("t1 HERE: \n")
print(t1.url)
print(interpret_functionality_TREE(t1.acc_tree))
# print("t2 HERE: \n")
# print(t2.url)
# print(interpret_functionality_TREE(t2.acc_tree))

# embed_product_1 = [get_embedding(product_1)]
# embed_product_2 = [get_embedding(product_2)]
# embed_office_prods = [get_embedding(office_prods)]
'''
print(f"Sanity, should be 1: {cosine_similarity(embed_product_1, embed_product_1)}")

print(f"Similarity between {product_1} and {product_2}: {cosine_similarity(embed_product_1, embed_product_2)}")
print(f"Similarity between {product_1} and {office_prods}: {cosine_similarity(embed_product_1, embed_office_prods)}")
print(f"Similarity between {product_2} and {office_prods}: {cosine_similarity(embed_product_2, embed_office_prods)}")
'''
