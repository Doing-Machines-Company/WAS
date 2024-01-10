
from urllib.parse import urlparse, urlunparse

def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')

def trim_url_to_depth(url, depth):
    parsed = urlparse(url)

    path_segments = parsed.path.split('/')
    trimmed_path = '/'.join(path_segments[:depth + 1])

    trimmed_url = urlunparse((parsed.scheme, parsed.netloc, trimmed_path, '', '', ''))
    return trimmed_url
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

class InferenceWebPageNode:
    def __init__(self, url, private, public, acc_tree, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private if public is None else public
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
        return (f"InferenceWebPageNode(URL: {self.url}, Private: {self.private}, "
                f"Public: {self.public}, Parent URL: {parent_url}, "
                f"Children URLs: [{children_urls}]")