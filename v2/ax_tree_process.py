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


def process_axtree_action(obs: AxObservation):
    counter = 1
    action_list = [Action(Action.Type.STOP, None, None)]
    cleaned_tree = "[0] STOP: STOP AND FINISH\n"
    # TODO ADD UTILITY MORE HERE
    # TODO ADD GO BACK ACTION


    for i in range(len(obs.nodes_info)):
        if obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'])
            reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
            if node_action:
                action_list.append(node_action)
                if ('radio' in obs.nodes_info[i]['html'] or 'checkbox' in obs.nodes_info[i]['html'] or '<input' in obs.nodes_info[i]['html']) and len(reqs) > 0:
                    if node_action.action_type == Action.Type.INPUT:
                        cleaned_tree += f"[{counter}]{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {reqs}\n"
                    else:
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

def process_axtree_memory(old_obs: AxObservation, new_obs: AxObservation):
    old_tree_cleaned = "[0] STOP: STOP AND FINISH\n"
    new_tree_cleaned = "[0] STOP: STOP AND FINISH\n"
    old_obs_counter = 1
    new_obs_counter = 1

    for i in range(len(old_obs.nodes_info)):
        if old_obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(old_obs.nodes_info[i]['xpath'], old_obs.nodes_info[i]['html'])
            reqs = [prop for prop in old_obs.nodes_info[i]['properties'] if 'required' in prop]
            if node_action:
                if ('radio' in old_obs.nodes_info[i]['html'] or 'checkbox' in old_obs.nodes_info[i]['html'] or '<input' in
                    old_obs.nodes_info[i]['html']) and len(reqs) > 0:
                    if node_action.action_type == Action.Type.INPUT:
                        old_tree_cleaned += f"[{old_obs_counter}]{old_obs.nodes_info[i]['indent']}input: {old_obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        old_tree_cleaned += f"[{old_obs_counter}]{old_obs.nodes_info[i]['indent']}{old_obs.nodes_info[i]['role']}: {old_obs.nodes_info[i]['name']} {reqs}\n"
                else:
                    old_tree_cleaned += f"[{old_obs_counter}]{old_obs.nodes_info[i]['indent']}{old_obs.nodes_info[i]['role']}: {old_obs.nodes_info[i]['name']}\n"
            else:
                old_tree_cleaned += f"{old_obs.nodes_info[i]['indent']}{old_obs.nodes_info[i]['role']}: {old_obs.nodes_info[i]['name']}\n"
        else:
            old_tree_cleaned += f"{old_obs.nodes_info[i]['indent']}{old_obs.nodes_info[i]['role']}: {old_obs.nodes_info[i]['name']}\n"

    for i in range(len(new_obs.nodes_info)):
        if new_obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(new_obs.nodes_info[i]['xpath'], new_obs.nodes_info[i]['html'])
            reqs = [prop for prop in new_obs.nodes_info[i]['properties'] if 'required' in prop]
            if node_action:
                if ('radio' in new_obs.nodes_info[i]['html'] or 'checkbox' in new_obs.nodes_info[i]['html'] or '<input' in
                    new_obs.nodes_info[i]['html']) and len(reqs) > 0:
                    if node_action.action_type == Action.Type.INPUT:
                        new_tree_cleaned += f"[{new_obs_counter}]{new_obs.nodes_info[i]['indent']}input: {new_obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        new_tree_cleaned += f"[{new_obs_counter}]{new_obs.nodes_info[i]['indent']}{new_obs.nodes_info[i]['role']}: {new_obs.nodes_info[i]['name']} {reqs}\n"
                else:
                    new_tree_cleaned += f"[{new_obs_counter}]{new_obs.nodes_info[i]['indent']}{new_obs.nodes_info[i]['role']}: {new_obs.nodes_info[i]['name']}\n"
            else:
                new_tree_cleaned += f"{new_obs.nodes_info[i]['indent']}{new_obs.nodes_info[i]['role']}: {new_obs.nodes_info[i]['name']}\n"
        else:
            new_tree_cleaned += f"{new_obs.nodes_info[i]['indent']}{new_obs.nodes_info[i]['role']}: {new_obs.nodes_info[i]['name']}\n"

    return old_tree_cleaned, new_tree_cleaned
