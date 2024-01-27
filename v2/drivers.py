import re
from playwright.sync_api import sync_playwright
from models import WebDriver, Action
from models import PageObservation
class AxObservation(PageObservation):
    def __init__(self, axtree):
        self.axtree = axtree
    def __eq__(self):
        pass
    def __str__(self):
        node_id_to_idx = {}
        for idx, node in enumerate(self.axtree):
            node_id_to_idx[node["nodeId"]] = idx

        obs_nodes_info = {}

        def dfs(idx: int, obs_node_id: str, depth: int) -> str:
            tree_str = ""
            node = self.axtree[idx]
            indent = "\t" * depth
            valid_node = True
            try:
                role = node["role"]["value"]
                name = node["name"]["value"]
                node_str = f"[{obs_node_id}] {role} {repr(name)}"
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

                if properties:
                    node_str += " " + " ".join(properties)

                # check valid
                if not node_str.strip():
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
                    tree_str += f"{indent}{node_str}"
                    obs_nodes_info[obs_node_id] = {
                        "backend_id": node["backendDOMNodeId"],
                        "text": node_str,
                        "html" : node["html"]
                    }
            except Exception as e:
                valid_node = False

            for _, child_node_id in enumerate(node["childIds"]):
                if child_node_id not in node_id_to_idx:
                    continue
                # mark this to save some tokens
                child_depth = depth + 1 if valid_node else depth
                child_str = dfs(
                    node_id_to_idx[child_node_id], child_node_id, child_depth
                )
                if child_str.strip():
                    if tree_str.strip():
                        tree_str += "\n"
                    tree_str += child_str

            return tree_str

        tree_str = dfs(0, self.axtree[0]["nodeId"], 0)
        """further clean accesibility tree"""
        clean_lines: list[str] = []
        for line in tree_str.split("\n"):
            # remove statictext if the content already appears in the previous line
            if "statictext" in line.lower():
                prev_lines = clean_lines[-3:]
                pattern = r"\[\d+\] StaticText (.+)"

                match = re.search(pattern, line, re.DOTALL)
                if match:
                    static_text = match.group(1)[1:-1]  # remove the quotes
                    if static_text and all(
                        static_text not in prev_line
                        for prev_line in prev_lines
                    ):
                        clean_lines.append(line)
            else:
                clean_lines.append(line)

        return "\n".join(clean_lines)
class MyDriver(WebDriver):
    def __init__(self, agent, knowledge_base, client): 
        super().__init__(agent, knowledge_base)
        self.client = client
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
    def apply(a : Action):
        pass

#temporary setup
context_manager = sync_playwright()
playwright = context_manager.__enter__()
browser = playwright.chromium.launch(
headless=False)
context = browser.new_context()
page = context.new_page()
client = page.context.new_cdp_session(page)  # talk to chrome devtools
client.send("Accessibility.enable")
page.client = client  # type: ignore # TODO[shuyanzh], fix this hackey client
url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sports-outdoors.html'
page.goto(url)
# set the first page as the current page
page = context.pages[0]
page.bring_to_front()


driver = MyDriver("agent", "poopfare", page.client)
print(str(driver.observe_state()))

