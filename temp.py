
def process_axtree_memory(obs: AxObservation):
    tree_cleaned = "[0] STOP: STOP AND FINISH\n"
    obs_counter = 1

    for i in range(len(obs.nodes_info)):
        if obs.nodes_info[i]['role'] != 'RootWebArea':
            node_action = extract_interaction_info(obs.nodes_info[i]['xpath'], obs.nodes_info[i]['html'])
            reqs = [prop for prop in obs.nodes_info[i]['properties'] if 'required' in prop]
            if node_action:
                if ('radio' in obs.nodes_info[i]['html'] or 'checkbox' in obs.nodes_info[i]['html'] or '<input' in
                    obs.nodes_info[i]['html']) and len(reqs) > 0:
                    if node_action.action_type == Action.Type.INPUT:
                        tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}input: {obs.nodes_info[i]['name']} {reqs}\n"
                    else:
                        tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']} {reqs}\n"
                else:
                    tree_cleaned += f"[{obs_counter}]{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
            else:
                tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"
        else:
            tree_cleaned += f"{obs.nodes_info[i]['indent']}{obs.nodes_info[i]['role']}: {obs.nodes_info[i]['name']}\n"


    return tree_cleaned
