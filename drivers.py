import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
# from impls import *
from action import Action
from dataclasses import dataclass


@dataclass
class DivAttributes:
    div_id: str
    div_class: str

class AxObservation(PageObservation):
    def __init__(self, axtree, url):
        self.axtree = axtree
        self.url = url
        node_id_to_idx = {}
        for idx, node in enumerate(self.axtree):
            node_id_to_idx[node["nodeId"]] = idx

        self.nodes_info = []
        # self.div_attributes = {}

        # def find_enclosing_divs(node: dict, tree: list[dict]) -> list[str]:
        #     enclosing_divs = []
        #     parent_id = node.get('parentId')
        #     while parent_id is not None:
        #         parent_node = next((n for n in tree if n['nodeId'] == parent_id), None)
        #         if parent_node is None:
        #             break
        #         if 'div' in parent_node.get('html', ''):
        #             enclosing_divs.append(parent_node['nodeId'])
        #         parent_id = parent_node.get('parentId')
        #     return enclosing_divs

        def dfs(idx: int, obs_node_id: str, depth: int) -> str:
            pua_cleaner = re.compile('[\ue000-\uf8ff]')
            node = self.axtree[idx]
            indent = "\t" * depth
            valid_node = True
            include_in_nodes_info = True
            try:
                role = node["role"]["value"]
                name = node["name"]["value"]
                name = pua_cleaner.sub('', name)
                properties = []
                for property in node.get("properties", []):
                    try:
                        ignored_properties = {"focusable", "editable", "readonly", "level", "settable", "multiline", "invalid"}
                        if property["name"] in ignored_properties:
                            continue
                        properties.append(f'{property["name"]}: {property["value"]["value"]}')
                    except KeyError:
                        pass
                # check valid
                if not role and not name.strip():
                    valid_node = False

                # empty generic node
                if not name.strip():
                    # if not properties:
                    if role in ["generic", "img", "list", "strong", "paragraph", "banner", "navigation", "Section",
                                "LabelText", "Legend", "listitem", "LineBreak", "ListMarker", "gridcell", "link"]:  # TODO, double check logic, I did this arbitrarily ripping things out
                        include_in_nodes_info = False
                    # elif role in ["listitem"]:
                    #     include_in_nodes_info = False

                if valid_node:
                    # enclosing_divs = find_enclosing_divs(node, self.axtree)
                    if include_in_nodes_info:
                        node_info = {
                            "nodeId": obs_node_id,
                            "name": name,
                            "role": role,
                            "indent": indent,
                            "properties": properties,
                            "html": node['html'],
                            "xpath": node['xpath'],
                            "parentId": node['parentId'] if 'parentId' in node else None,
                            # "enclosing_divs": enclosing_divs
                        }
                        self.nodes_info.append(node_info)

                    # if role == 'generic' and 'div' in node.get('html', ''):
                    #     div_id = get_div_id(node)
                    #     div_class = get_div_class(node)

                        # div_attributes = DivAttributes(div_id=div_id, div_class=div_class)
                        # self.div_attributes[obs_node_id] = div_attributes

            except Exception as e:
                valid_node = False

            for _, child_node_id in enumerate(node["childIds"]):
                if child_node_id not in node_id_to_idx:
                    continue
                # mark this to save some tokens
                child_depth = depth + 1 if valid_node and include_in_nodes_info else depth
                dfs(node_id_to_idx[child_node_id], child_node_id, child_depth)

        dfs(0, self.axtree[0]["nodeId"], 0)
        """further clean accesibility tree"""
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
        self.nodes_info = cleaned_nodes

    def __eq__(self):
        pass

    def __str__(self):
        tree_str = ''
        for node in self.nodes_info:
            tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str

def get_div_id(node):
    return node.get('attributes', {}).get('id', '')

def get_div_class(node):
    return node.get('attributes', {}).get('class', '')

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
                remote_object_id = remote_object["object"]["objectId"] # MAY BE ABLE TO FIND ELEMENT GIVEN REMOTE OBJECT ID, NO NEED FOR XPATHS
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
                node['xpath'] = ''
                if 'html' not in node:
                    node['html'] = ''
                continue
        url = self.client.send("Runtime.evaluate", {
            "expression": "location.href",
            "returnByValue": True
        })["result"]["value"]
        observation = AxObservation(accessibility_tree, url)
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

            case Action.Type.CLICK_IMPORTANT:
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

            case Action.Type.CLICK_CHECKBOX:
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

            case Action.Type.CLICK_RADIO:
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
                print("INPUTTING")
                print(target_xpath)
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

            case Action.Type.GET_NEXT_SUBTASK_FINISHED:
                pass

            case Action.Type.GET_NEXT_SUBTASK_IMPOSSIBLE:
                pass

            case Action.Type.STOP:
                input("ABOUT TO STOP")
                exit()

            case Action.Type.GOTO_URL: # haven't tested
                self.page.goto(a.input_string)
                self.page.wait_for_load_state('networkidle')

            case Action.Type.GO_BACK:
                # self.page.go_back() not actually using go_back as occasionally the last page is not useful, need to make better this is jank
                self.page.goto(a.input_string)
                self.page.wait_for_load_state('networkidle')



