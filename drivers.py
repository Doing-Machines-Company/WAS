import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
from impls import *
from action import Action
class AxObservation(PageObservation):
    def __init__(self, axtree, client):
        self.axtree = axtree
        self.url = client.send("Runtime.evaluate", {
            "expression": "location.href",
            "returnByValue": True
        })["result"]["value"]
        node_id_to_idx = {}
        for idx, node in enumerate(self.axtree):
            node_id_to_idx[node["nodeId"]] = idx

        self.nodes_info = []

        def dfs(idx: int, obs_node_id: str, depth: int) -> str:
            pua_cleaner = re.compile('[\ue000-\uf8ff]')
            tree_str = ""
            node = self.axtree[idx]
            indent = "\t" * depth
            valid_node = True
            try:
                role = node["role"]["value"]
                name = node["name"]["value"]
                name = pua_cleaner.sub('', name)
                properties = []
                for property in node.get("properties", []):
                    try:
                        ignored_properties = {"focusable","editable","readonly","level","settable", "multiline","invalid",}
                        if property["name"] in ignored_properties:
                            continue
                        properties.append(
                            f'{property["name"]}: {property["value"]["value"]}'
                        )
                    except KeyError:
                        pass
                # check valid
                if not role and not name:
                    valid_node = False

                # empty generic node
                if not name.strip():
                    if not properties:
                        if role in [
                            "generic",
                            "img",
                            "list",
                            "strong",
                            "paragraph",
                            "banner",
                            "navigation",
                            "Section",
                            "LabelText",
                            "Legend",
                            "listitem",
                        ]:
                            valid_node = False
                    elif role in ["listitem"]:
                        valid_node = False
    
                if valid_node:
                    node_info = {
                        "nodeId": obs_node_id,
                        "name" : name,
                        "role" : role,
                        "indent" : indent,
                        "properties" : properties,
                        "html" : node['html'],
                        "xpath" : node['xpath']
                    }
                    self.nodes_info.append(node_info)
            except Exception as e:
                valid_node = False

            for _, child_node_id in enumerate(node["childIds"]):
                if child_node_id not in node_id_to_idx:
                    continue
                # mark this to save some tokens
                child_depth = depth + 1 if valid_node else depth
                dfs(
                    node_id_to_idx[child_node_id], child_node_id, child_depth
                )

        dfs(0, self.axtree[0]["nodeId"], 0)
        # print(self.nodes_info)
        """further clean accesibility tree"""
        #maybe make this part single pass? - TODO CEM
        cleaned_nodes = []
        for node in self.nodes_info:
            # remove statictext if the content already appears in the previous line
            if node["role"] == "StaticText":
                prev_nodes = cleaned_nodes[-3:]
                found = False
                for prev in prev_nodes:
                    if node["name"] in prev["name"]:
                        found = True
                if found:
                    continue
            cleaned_nodes.append(node)
        # self.nodes_info = cleaned_nodes
    def __eq__(self):
        pass
    def __str__(self):
        tree_str = ''
        for node in self.nodes_info:
            tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str

class MyDriver(WebDriver):
    def __init__(self, agent, knowledge_base, page):
        super().__init__(agent, knowledge_base)
        self.client = page.client
        self.page = page
        agent.new_obs = self.observe_state()
        # print(agent.new_obs.nodes_info)

    def observe_state(self) -> PageObservation:
        accessibility_tree = self.client.send(
            "Accessibility.getFullAXTree", {}
        )["nodes"]
        seen_ids = set()
        _accessibility_tree = []
        for node in accessibility_tree:
            if node["nodeId"] not in seen_ids:
                _accessibility_tree.append(node)
                seen_ids.add(node["nodeId"])
        accessibility_tree = _accessibility_tree
        for node in accessibility_tree:
            if "backendDOMNodeId" not in node:
                continue
            backend_node_id = str(node["backendDOMNodeId"])
            try:
                remote_object = self.client.send(
                    "DOM.resolveNode", {"backendNodeId": int(backend_node_id)}
                )
                remote_object_id = remote_object["object"]["objectId"]
                xpath_script = '''
                        function() {
                            function getXPath(element) {
                                if (!element || !element.parentNode) {
                                    return null;
                                }
                                if (element.id) {
                                    return 'id("' + element.id + '")';
                                }
                                if (element === document.body) {
                                    return element.tagName.toLowerCase();
                                }
                                var ix = 0;
                                var siblings = element.parentNode.childNodes;
                                for (var i = 0; i < siblings.length; i++) {
                                    var sibling = siblings[i];
                                    if (sibling === element) {
                                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                    }
                                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) {
                                        ix++;
                                    }
                                }
                            }
                            return getXPath(this);
                        }
                        '''

                xpath_response = self.client.send(
                    "Runtime.callFunctionOn",
                    {
                        "objectId": remote_object_id,
                        "functionDeclaration": xpath_script,
                        "returnByValue": True
                    }
                )
                node_xpath = xpath_response["result"]["value"]
                response = self.client.send(
                    "DOM.getOuterHTML",
                    {
                        "objectId" : remote_object_id,
                    },
                )
                node["html"]=response["outerHTML"]
                node["xpath"] = node_xpath
            except Exception as e:
                continue
        observation = AxObservation(accessibility_tree, self.client)
        return observation

    def apply(self, a : Action): # TODO NEED TO MAKE LESS BAD
        action_type = a.action_type
        target_html = a.html
        target_xpath = a.xpath
        locator = self.page.locator(f'xpath={target_xpath}')
        match action_type:
            case Action.Type.CLICK_LINK:
                try:
                    element_handle_response = self.client.send(
                        "Runtime.evaluate",
                        {
                            "expression": f"document.evaluate('{target_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue",
                            "returnByValue": False
                        }
                    )
                    element_object_id = element_handle_response['result']['objectId']

                    self.client.send( # SHOULD I SCROLL???
                        "Runtime.callFunctionOn",
                        {
                            "objectId": element_object_id,
                            "functionDeclaration": "function() { this.scrollIntoViewIfNeeded(); }",
                            "returnByValue": False
                        }
                    )

                    self.client.send(
                        "Runtime.callFunctionOn",
                        {
                            "objectId": element_object_id,
                            "functionDeclaration": "function() { this.click(); }",
                            "returnByValue": False
                        }
                    )
                except Exception as e:
                    print(f"Error clicking element: {e}")

            case Action.Type.CLICK_GENERAL:
                try:
                    element_handle_response = self.client.send(
                        "Runtime.evaluate",
                        {
                            "expression": f"document.evaluate('{target_xpath}', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue",
                            "returnByValue": False
                        }
                    )
                    element_object_id = element_handle_response['result']['objectId']

                    self.client.send(  # SHOULD I SCROLL???
                        "Runtime.callFunctionOn",
                        {
                            "objectId": element_object_id,
                            "functionDeclaration": "function() { this.scrollIntoViewIfNeeded(); }",
                            "returnByValue": False
                        }
                    )

                    self.client.send(
                        "Runtime.callFunctionOn",
                        {
                            "objectId": element_object_id,
                            "functionDeclaration": "function() { this.click(); }",
                            "returnByValue": False
                        }
                    )
                except Exception as e:
                    print(f"Error clicking element: {e}")

            case Action.Type.INPUT:
                input_text = a.input_string
                try:
                    self.page.wait_for_load_state('networkidle')
                    locator.first.fill(input_text)
                    self.page.wait_for_load_state('networkidle')
                    if "search" in target_html:
                        print("SEARCHING PRESS ENTER")
                        self.page.keyboard.press('Enter')
                        self.page.wait_for_load_state('networkidle')

                except Exception as e:
                    print(f"Error inputting element: {e}")
            case Action.Type.STOP:
                input("ABOUT TO STOP")
                exit()



