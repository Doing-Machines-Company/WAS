from drivers import AxObservation
from impls import *
from action import Action
def extract_interaction_info(xpath, html): #use general input type
    if '<a' in html:
        return Action(Action.Type.CLICK, xpath, html)
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "type=\"radio\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and ("<div" not in html): # filter out div?
        return Action(Action.Type.CLICK, xpath, html)
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html and "type=\"radio\"" not in html:
        return Action(Action.Type.INPUT, xpath, html)
    if "type=\"checkbox\"" in html:
        return Action(Action.Type.CLICK, xpath, html)
    if "<option" in html: # TODO DOUBLE CHECK THIS CAN ACTUALLY BE CLICKED
        return Action(Action.Type.CLICK, xpath, html)

    return None


def process_axtree(obs: AxObservation):
    counter = 0
    action_list = []
    cleaned_tree = ""

    for i in range(len(obs.nodes_info)):
        # print("XPATHH")
        # print(obs.nodes_info[i]['xpath'])
        if obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'])
            reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
            if node_action:
                action_list.append(node_action)
                if ('radio' in obs.nodes_info[i]['html'] or 'checkbox' in obs.nodes_info[i]['html'] or '<input' in obs.nodes_info[i]['html']) and len(reqs) > 0:
                    print(f"{i}: {obs.nodes_info[i]['html']}")
                    cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {reqs}\n"
                else:
                    cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
                counter += 1
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        else:
            cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
    print(cleaned_tree)
    return cleaned_tree, action_list