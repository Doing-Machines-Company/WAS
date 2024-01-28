from drivers import AxObservation
from impls import *
from action import Action
def extract_interaction_info(html): #use general input type
    if '<a' in html:
        return Action(Action.Type.CLICK, html)
    if ('<button' in html or "type='button'" in html or "role='button'" in html or "role=\"button\"" in html or "type=\"radio\"" in html or "[onclick]" in html or "onclick=" in html or "[role='button']" in html) and ("<div" not in html): # filter out div?
        return Action(Action.Type.CLICK, html)
    if ("<input" in html or "textarea" in html) and "type=\"checkbox\"" not in html and "type=\"radio\"" not in html:
        return Action(Action.Type.INPUT, html)
    if "type=\"checkbox\"" in html:
        return Action(Action.Type.CLICK, html)
    if "<option" in html: # TODO DOUBLE CHECK THIS CAN ACTUALLY BE CLICKED
        return Action(Action.Type.CLICK, html)

    return None


def process_axtree(obs: AxObservation):
    counter = 0
    action_list = []
    cleaned_tree = ""

    for i in range(len(obs.nodes_info)):
        if obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(obs.nodes_info[i]['html'])
            if node_action:
                action_list.append(node_action)
                cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
                counter += 1
            else:
                cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        else:
            cleaned_tree += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"

    return cleaned_tree, action_list