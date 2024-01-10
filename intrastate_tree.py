import json

import copy


class IntrastateWebPageNode:
    def __init__(self, url=None, edge=None, private=None, acc_tree=None, embedding=None): # represented by url and action, action taken at url/state
        self.url = url
        self.edge = edge # something like (action, html of action)
        self.private = private # effect of edge operation on parent
        self.public = None # functionality of all children operations
        self.parent = None
        self.trajectory = [] # How you got here from root

        self.acc_tree = acc_tree
        self.children = []
        self.page_embedding = embedding

    def add_child(self, child):
        self.children.append(child)
        child.parent = self
        child.trajectory = copy.deepcopy(self.trajectory)
        child.trajectory.append(child.edge)

def deserialize_intrastate(node_data):
    """ Deserialize a node dictionary into an IntrastateWebPageNode object. """
    node = IntrastateWebPageNode(
        url=node_data['url'],
        edge=node_data['edge'],
        private=node_data['private'],
        acc_tree=node_data['acc_tree']
    )

    for child_data in node_data['children']:
        child_node = deserialize_intrastate(child_data)
        node.add_child(child_node)

    return node

def load_intrastate_from_json(filename):
    with open(filename, 'r') as file:
        data = json.load(file)
        return deserialize_intrastate(data)