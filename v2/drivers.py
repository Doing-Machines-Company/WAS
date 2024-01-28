import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
from impls import *
from action import Action
class AxObservation(PageObservation):
    def __init__(self, axtree):
        self.axtree = axtree
    
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
                    #print("HERE")
                    node_info = {
                        "nodeId": obs_node_id,
                        "name" : name,
                        "role" : role,
                        "indent" : indent,
                        "properties" : properties,
                        "html" : node['html'], 
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
        self.nodes_info = cleaned_nodes
    def __eq__(self):
        pass
    def __str__(self):
        tree_str = ''
        for node in self.nodes_info:
            tree_str += f"{node['indent']}[{node['nodeId']}] {node['role']} {repr(node['name'])} " + " ".join(node["properties"]) + "\n"
        return tree_str

class MyDriver(WebDriver):
    def __init__(self, agent, knowledge_base, client):
        super().__init__(agent, knowledge_base)
        self.client = client
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
                response = self.client.send(
                    "DOM.getOuterHTML",
                    {
                        "objectId" : remote_object_id,
                    },
                )
                node["html"]=response["outerHTML"]
            except Exception as e:
                continue
        observation = AxObservation(accessibility_tree)
        return observation

    def apply(self, a : Action): # TODO NEED TO MAKE LESS BAD
        action_type = a.action_type
        target_html = a.html
        print(target_html)
        match action_type:
            case Action.Type.CLICK:
                click_script = f"""
                    (function() {{
                        const elements = document.querySelectorAll('body *');
                        for (let element of elements) {{
                            if (element.outerHTML === `{target_html}`) {{
                                element.click();
                                return true;
                            }}
                        }}
                        return false;
                    }})();
                    """

                result = self.client.send("Runtime.evaluate", {"expression": click_script})
                print(f"CLICK FLAG {result['result']['value']}")
            case Action.Type.INPUT:
                input_text = "TESTING MODE"
                input_script = f"""
                    (function() {{
                        const elements = document.querySelectorAll('input');
                        for (let element of elements) {{
                            if (element.outerHTML === `{target_html}`) {{
                                element.value = `{input_text}`;
                                return true;
                            }}
                        }}
                        return false;
                    }})();
                    """
                result = self.client.send("Runtime.evaluate", {"expression": input_script})
                print(f"INPUT FLAG {result['result']['value']}")
            case Action.Type.STOP:
                input("ABOUT TO STOP")
                exit()



