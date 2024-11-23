# from scrape4 import *
from scrape7 import *
from bs4 import BeautifulSoup
from look_at_scrape import load_scraper_state
from utils.element_utils.element_similarity import element_similarity

eq_class_set = load_scraper_state('scrape_trials/scraper_state.pkl')
def analyze_equivalence_class(eq_class: EquivalenceClass):
    for page_state in eq_class.page_states.values():
        soup = BeautifulSoup(page_state.html, 'html.parser')

        def traverse_divs(div, level=0):
            if div.name == 'div' and div.get('id'):
                div_id = div['id']
                if div_id in eq_class.noted_divs:
                    return

                def has_matching_action(element_html):
                    for action in page_state.actions:
                        if element_similarity(str(element_html), action.html) > 0.9:
                            return True
                    return False

                if has_matching_action(div):
                    child_divs_with_same_id_and_actions = [child for child in div.find_all('div', recursive=False) if
                                                           child.get('id') == div_id and has_matching_action(child)]
                    if len(child_divs_with_same_id_and_actions) > 1:
                        for child_div in child_divs_with_same_id_and_actions:
                            traverse_divs(child_div, level + 1)
                    else:
                        eq_class.noted_divs[div_id] = None
                        print(f"Noted div with ID: {div_id} at level {level}")

            for child_div in div.find_all('div', recursive=False):
                traverse_divs(child_div, level + 1)

        traverse_divs(soup)

for eq_class in eq_class_set.classes:
    analyze_equivalence_class(eq_class)

for eq_class in eq_class_set.classes:
    print(f"Equivalence Class: {eq_class}")
    print("Noted Divs:")
    for div_id in eq_class.noted_divs:
        print(div_id)
