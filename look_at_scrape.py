import pickle
from pathlib import Path
from pprint import pprint
from scrape4 import *


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

def main():
    scraper_state_file = 'scrape_trials/scraper_state.pkl'
    equiv_classes = load_scraper_state(scraper_state_file)
    display_equivalence_classes(equiv_classes)

if __name__ == '__main__':
    main()