import os 
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(
                  os.path.dirname(__file__), 
                  os.pardir)
)
sys.path.append(PROJECT_ROOT)

from models.actions import *
from bs4 import BeautifulSoup
import time
from typing import Optional, List, Any

CDPSession = Any
AxNode = Any
def get_ax_tree(cdpSession: CDPSession) -> list[AxNode]:
    start = time.time()
    accessibility_tree = cdpSession.send(
        "Accessibility.getFullAXTree", {}
    )["nodes"]
    print("\tcdp js took", time.time() - start)
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
            remote_object = cdpSession.send(
                "DOM.resolveNode", {"backendNodeId": int(backend_node_id)}
            )
            remote_object_id = remote_object["object"][
                "objectId"]  # MAY BE ABLE TO FIND ELEMENT GIVEN REMOTE OBJECT ID, NO NEED FOR XPATHS
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

            xpath_response = cdpSession.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": remote_object_id,
                    "functionDeclaration": xpath_script,
                    "returnByValue": True
                }
            )
            node_xpath = xpath_response["result"]["value"]
            response = cdpSession.send(
                "DOM.getOuterHTML",
                {
                    "objectId": remote_object_id,
                },
            )
            node["html"] = response["outerHTML"]
            node["xpath"] = node_xpath
            node["action_effect"] = None

        except Exception as e:
            node['xpath'] = ''
            if 'html' not in node:
                node['html'] = ''
            continue

    return accessibility_tree


def ax_node_to_action(ax_node: AxNode, header_html: str, footer_html: str, url: str) -> IndefiniteAction | None:

    # NOTE: NO LONGER FILTER OUT HEADER AND FOOTER ACTIONS HERE

    possible_action_types = []

    important_clickables = [
        'button',
    ]

    general_clickables = [  # dialog clickable?
        'treeitem', 'switch', 'option', 'menuitemcheckbox',
        'menuitemradio',
        'slider', 'listbox', 'tree',
        'grid', 'alert', 'alertdialog',
        'log', 'marquee', 'timer', 'tooltip', 'banner',
        'complementary', 'contentinfo', 'form',
        'region', 'status', 'img', 'note', 'application',
        'cell', 'definition', 'directory', 'document',
        'feed', 'figure', 'group', 'img', 'list',
        'listitem',
        'option', 'tab']

    selects = [  # need menuitemcheckbox and menuitemradio? - JC
        'menuitem'
    ]

    input_roles = [
        'textbox',
        'checkbox', 'radio',
        'textarea'
    ]

    non_browser_attributes = [
        'mailto:',
        'tel:',
        'print()',
        'window.print()',
        'onclick="window.print()"',
        'printthis()',
        'onclick="printthis()"',
    ]
    ignored_roles = [
        'main',
        'article',
        'group',
        'dialog',
        'document',
        'navigation',
        'status',
        'alert',
        'complementary',
        'alertdialog',
        'grid'
    ]
    xpath = ax_node["xpath"]
    html = ax_node["html"]
    role = ax_node["role"]
    nodeId = ax_node["nodeId"]

    soup = BeautifulSoup(html, 'html.parser')

    if xpath and html and xpath.strip() != "" and html.strip() != "":
        # Check if the action is a pure link in the header or footer
        if role.strip () in ignored_roles:
            # return IndefiniteAction([], None, nodeId, IndefiniteAction.Location.UNDEFINED)  # may just want to return None?
            return None

        # if html in footer_html or (html in header_html and url not in 'https://www.dominos.com/en/'):
        #     return IndefiniteAction([], None, nodeId)

        #not sure what this does at all - Cem
        if any(attr in html.lower() for attr in non_browser_attributes):
            # return IndefiniteAction([], None, nodeId, IndefiniteAction.Location.UNDEFINED)
            return None

        if role.strip() == 'link':
            possible_action_types.append(Action.Type.CLICK_LINK)

        elif role.strip() in important_clickables:
            possible_action_types.append(Action.Type.CLICK_IMPORTANT)

        elif role.strip() == 'radio':
            # action = Action(Action.Type.CLICK_RADIO, xpath, html)
            # action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_RADIO)

        elif role.strip() == 'checkbox':
            possible_action_types.append(Action.Type.CLICK_CHECKBOX)

        elif role.strip() in general_clickables:
            # action = Action(Action.Type.CLICK_GENERAL, xpath, html)
            # action.set_tree_line(f"{role}: {ax_node['name']}")
            possible_action_types.append(Action.Type.CLICK_GENERAL)

        elif role.strip() in selects:
            possible_action_types.append(Action.Type.SELECT_GENERAL)

        elif role.strip() in input_roles or soup.find(('input', 'textarea')):

            # input_type = None
            #
            # input_element = soup.find('input')
            #
            # if input_element:
            #     input_type = input_element.get('type', '').lower()
            #
            # if input_type == 'checkbox' and Action.Type.CLICK_CHECKBOX not in possible_action_types:
            #     possible_action_types.append(Action.Type.CLICK_CHECKBOX)
            #
            # elif input_type == 'radio' and Action.Type.CLICK_RADIO not in possible_action_types:
            #     possible_action_types.append(Action.Type.CLICK_RADIO)
            #
            # else:
            possible_action_types.append(Action.Type.INPUT)


        elif soup.has_attr('contenteditable') and soup['contenteditable'].lower() == 'true':
            possible_action_types.append(Action.Type.INPUT)

    # input('tonkkk')
    if possible_action_types != []:
        # input(possible_action_types)
        action = Action(None, xpath, html)
        action.set_tree_line(f"{role}: {ax_node['name']}")
        action.set_desired_option(ax_node['name'])
        # if xpath and xpath == "id(\"tab-Delivery\")":
        #     print("FOUND DELIVERY OPTION")
        #     print(possible_action_types)
        if action and (action.html in header_html):
            return IndefiniteAction(possible_action_types, action, nodeId, IndefiniteAction.Location.HEADER)
        elif action and (action.html in footer_html):
            # return IndefiniteAction(possible_action_types, action, nodeId, IndefiniteAction.Location.FOOTER)
            return None
        else:
            return IndefiniteAction(possible_action_types, action, nodeId, IndefiniteAction.Location.BODY)
    else:
        return None