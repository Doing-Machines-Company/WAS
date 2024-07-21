from utils.element_utils.element_similarity import element_similarity

def action_intersect(action_list1, action_list2):
    same_actions = []
    for action_html_1 in action_list1:
        for action_html_2 in action_list2:
            sim = element_similarity(action_html_1, action_html_2)
            if sim > 0.6:
                same_actions.append(action_html_1)
    return same_actions