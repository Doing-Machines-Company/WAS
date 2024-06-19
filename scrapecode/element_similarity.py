from playwright.sync_api import sync_playwright
import difflib
from io import StringIO
import json
from html.parser import HTMLParser
from bs4 import BeautifulSoup


def get_element_details(html):
    """
    Extracts details of action elements, focusing on titles for all elements.
    Only considers <span> elements with class="a-text-bold" for text details.
    """
    soup = BeautifulSoup(html, 'html.parser')
    titles = []
    # TODO, NEED STRICTER FOR INPUTS, DO NOT FALSELY MATCH INPUTS
    for element in soup.find_all(['a', 'button', 'input', 'span']):
        if element.name == 'span' and 'a-text-bold' in element.get('class', []):
            text = element.text.strip()
            if text:
                if isinstance(text, str):
                    titles.append(text)
                elif isinstance(text, list):
                    titles.extend(text)
                else:
                    assert False, f"Unexpected title type: {type(text)}"
        elif element.name in ['button']: # Buttons want class, as a lot of buttons duplicate a lot, just have very low tolerance
            title = element.get('class') or element.text.strip()
            if title:
                if isinstance(title, str):
                    titles.append(title)
                elif isinstance(title, list):
                    titles.extend(title)
                else:
                    assert False, f"Unexpected title type: {type(title)}"
        elif element.name in ['input']:
            title = element.get('id') or element.text.strip()
            if title:
                if isinstance(title, str):
                    titles.append(title)
                elif isinstance(title, list):
                    titles.extend(title)
                else:
                    assert False, f"Unexpected title type: {type(title)}"
        elif element.name in ['a']: # This
            title = element.get('class') or element.text.strip()
            if title:
                if isinstance(title, str):
                    titles.append(title)
                elif isinstance(title, list):
                    titles.extend(title)
                else:
                    assert False, f"Unexpected title type: {type(title)}"
    return titles


def get_classes_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    all_classes = set()
    for element in soup.find_all(True, class_=True):
        classes = element.get('class', [])
        all_classes.update(classes)
    return all_classes


def jaccard_similarity(set1, set2):
    intersection = len(set1 & set2)
    if not set1 and not set2:
        return 1.0
    denominator = (len(set1) + len(set2) - intersection)
    return intersection / denominator if denominator else 0


class TagExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_endtag(self, tag):
        self.tags.append(tag)

    def handle_comment(self, data):
        self.tags.append('comment')


def get_tags(html_content):
    parser = TagExtractor()
    parser.feed(html_content)
    return parser.tags


def structural_similarity(document_1, document_2):
    diff = difflib.SequenceMatcher(None, get_tags(document_1), get_tags(document_2))
    return diff.ratio()


def style_similarity(document_1, document_2):
    classes_page1 = get_classes_from_html(document_1)
    classes_page2 = get_classes_from_html(document_2)
    return jaccard_similarity(classes_page1, classes_page2)


def element_similarity(document_1, document_2, k=0.6):
    details1 = get_element_details(document_1)
    details2 = get_element_details(document_2)

    # Check that all action elements have the same type and visible/title text
    # print(details1)
    # print(details2)
    # if sorted(details1) != sorted(details2):
    #     # print("Action elements do not match in type or visible text.")
    #     return 0

    # Proceed with the original similarity checks if the action elements match
    structural_sim = structural_similarity(document_1, document_2)
    style_sim = style_similarity(document_1, document_2)
    # print(f"Structural Similarity: {structural_sim}")
    # print(f"Style Similarity: {style_sim}")

    return min(structural_sim, style_sim)  # Structural sim seems to be more telling


# with open('el3.json', 'r') as file:
#     data = json.load(file)
#     document_1 = data["my_string"]
#
# with open('el1.json', 'r') as file:
#     data = json.load(file)
#     document_2 = data["my_string"]
#
# similarity_score = element_similarity(document_1, document_2)
# print(f"Similarity Score: {similarity_score}")
