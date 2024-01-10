import asyncio
from playwright.async_api import async_playwright
import re
from openai import OpenAI
import os
from urllib.parse import urlparse, urlunparse
import json
import copy

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





    def __eq__(self, other):
        if other is None:
            return False
        return self.url == other.url

    def __hash__(self):
        return hash(self.url)



def deserialize_node(node_data, parent=None):
    # Recreate a WebPageNode from the dictionary data.
    node = WebPageNode(
        url=node_data["url"],
        private=node_data["private"],
        public=node_data["public"],
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

def serialize_tree(root_node):
    return root_node.to_dict()

root_node = load_tree_from_file('webpage_MVP_V5.json')

node_kids = copy.copy(root_node.children)

for child in node_kids:
    print(child.url)
    merge = input("Merge? (y/n)")
    if merge == 'y' and child.children is not None:
        root_node.children.remove(child)
        root_node.children = root_node.children.union(child.children)
    else:
        pass

tree_data = serialize_tree(root_node)
with open('webtreeflattened.json', 'w', encoding='utf-8') as file:
    json.dump(tree_data, file, ensure_ascii=False, indent=4)
