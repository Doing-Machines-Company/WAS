import pickle
from pathlib import Path
from pprint import pprint
from scrape6 import *


def load_scraper_state(file_path: str):
    with open(file_path, 'rb') as f:
        return pickle.load(f)

def display_equivalence_classes(equiv_classes):
    print(f"Total Equivalence Classes: {len(equiv_classes.classes)}")
    print("Equivalence Classes:")
    for i, eq_class in enumerate(equiv_classes.classes, start=1):
        print(f"\nEquivalence Class {i}:")
        print(f"  Page URLs: {eq_class.page_urls}")
        print(f"  Total Unique Actions: {len(eq_class.unique_actions)}")
        print("  Unique Actions:")
        for j, (action_key, action_info) in enumerate(eq_class.unique_actions.items(), start=1):
            print(f"    Action {j}:")
            # print(f"      Action HTML: {action_info.action.html}")
            # print(f"      Action XPath: {action_info.action.xpath}")
            # print(f"      Before HTML: {action_info.before_html[:100]}...")
            # print(f"      After HTML: {action_info.after_html[:100]}...")
            print(f"      Before Screenshot: {action_info.before_screenshot}")
            print(f"      After Screenshot: {action_info.after_screenshot}")
            print(f"      Tree Line: {action_info.action.tree_line}")
            print()

        input("Press Enter to continue to the next equivalence class...")

def get_div_content(file_path, div_number):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    div_start = f"(Div {div_number})"
    div_end = f"(/Div {div_number})"

    inside_div = False
    div_content = []

    for line in lines:
        if line.strip() == div_start:
            inside_div = True
        elif line.strip() == div_end:
            inside_div = False
        elif inside_div and '(Div' not in line and '(/Div' not in line:
            div_content.append(line)

    return ''.join(div_content)
def main():
    scraper_state_file = 'scrape_supreme/scraper_state.pkl'
    equiv_classes = load_scraper_state(scraper_state_file)
    display_equivalence_classes(equiv_classes)
    # print(get_div_content("enum_cleaned.txt", 38))

if __name__ == '__main__':
    main()