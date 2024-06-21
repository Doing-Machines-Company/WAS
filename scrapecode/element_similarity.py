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
    def __init__(self, include_values=False, include_tags=True):
        super().__init__()
        self.structure = []
        self.include_values = include_values
        self.include_tags = include_tags

    def handle_starttag(self, tag, attrs):
        attr_names = [attr for attr in attrs] if self.include_values else [attr[0] for attr in attrs]
        if self.include_tags:
            self.structure.append((tag, attr_names))
        else:
            self.structure.append(tag)

    def handle_endtag(self, tag):
        self.structure.append(('/' + tag, []))

    def handle_comment(self, data):
        self.structure.append(('comment', []))


def get_structure(html_content):
    parser = TagExtractor()
    parser.feed(html_content)
    return parser.structure


def structural_similarity(document_1, document_2):
    structure1 = get_structure(document_1)
    structure2 = get_structure(document_2)

    print("STRUCTURAL")
    print(f"OF DOC 1: {structure1}")
    print(f"OF DOC 2: {structure2}")
    print("STRUCTURAL")

    # Convert structures to strings for comparison
    str1 = json.dumps(structure1)
    str2 = json.dumps(structure2)

    diff = difflib.SequenceMatcher(None, str1, str2)
    return diff.ratio()


def style_similarity(document_1, document_2):
    classes_page1 = get_classes_from_html(document_1)
    classes_page2 = get_classes_from_html(document_2)
    print("CLASSES")
    print(f"OF DOC 1: {classes_page1}")
    print(f"OF DOC 2: {classes_page2}")
    print("CLASSES")
    return jaccard_similarity(classes_page1, classes_page2)


def element_similarity(document_1, document_2, k=0.6):
    structural_sim = structural_similarity(document_1, document_2)
    style_sim = style_similarity(document_1, document_2)

    return min(structural_sim, style_sim)  # Structural sim seems to be more telling


string1 = "<a class=\"css-0\" data-quid=\"main-navigation-order-online\" href=\"/en/pages/order/\">Order Online</a>"
string2 = "<a data-quid=\"location\" href=\"/en/pages/order/?locations=1#!/locations/\" class=\"css-0\">Locations</a>"


similarity_score = element_similarity(string1, string2)
print(f"Similarity Score: {similarity_score}")
