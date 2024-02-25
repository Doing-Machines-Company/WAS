from playwright.sync_api import sync_playwright
import difflib
from io import StringIO
import json
from html.parser import HTMLParser
from bs4 import BeautifulSoup

def get_classes_from_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    all_classes = set()
    for element in soup.find_all(True,
                                 class_=True):  # True finds all tags, class_=True finds those with a class attribute
        classes = element.get('class', [])
        all_classes.update(classes)

    return all_classes

def jaccard_similarity(set1, set2):
    set1 = set(set1)
    set2 = set(set2)
    intersection = len(set1 & set2)

    if len(set1) == 0 and len(set2) == 0:
        return 1.0

    denominator = len(set1) + len(set2) - intersection
    return intersection / max(denominator, 0.000001)

def style_similarity(document_1, document_2):
    """
    Computes CSS style Similarity between two DOM trees using Playwright

    A = classes(Document_1)
    B = classes(Document_2)

    style_similarity = |A & B| / (|A| + |B| - |A & B|)

    :param url1: URL of the first page
    :param url2: URL of the second page
    :return: Number between 0 and 1 indicating similarity.
    """
    classes_page1 = get_classes_from_html(document_1)
    classes_page2 = get_classes_from_html(document_2)
    return jaccard_similarity(classes_page1, classes_page2)




class TagExtractor(HTMLParser):
    """
    A custom HTML parser designed to extract tags and comments from HTML content.
    """
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_endtag(self, tag):
        self.tags.append(tag)

    def handle_comment(self, data):
        self.tags.append('comment')

class EnhancedTagExtractor(HTMLParser):
    """
    An enhanced HTML parser designed to extract all types of tags,
    including self-closing tags, comments, and special tags like <!DOCTYPE>.
    """
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_endtag(self, tag):
        self.tags.append(f"/{tag}")

    def handle_comment(self, data):
        self.tags.append('comment')

    def handle_decl(self, decl):
        self.tags.append(f"!{decl}")

    def handle_startendtag(self, tag, attrs):
        # Specifically handle self-closing tags.
        self.tags.append(f"{tag}/")

class EnhancedTagExtractorWithoutImages(HTMLParser):
    """
    An enhanced HTML parser designed to extract all types of tags, excluding image tags,
    including self-closing tags, comments, and special tags like <!DOCTYPE>.
    """
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag != 'img':  # Ignore image tags
            self.tags.append(tag)

    def handle_endtag(self, tag):
        if tag != 'img':  # Ignore image tags
            self.tags.append(f"/{tag}")

    def handle_comment(self, data):
        self.tags.append('comment')

    def handle_decl(self, decl):
        self.tags.append(f"!{decl}")

    def handle_startendtag(self, tag, attrs):
        if tag != 'img':  # Specifically handle self-closing tags, ignoring images.
            self.tags.append(f"{tag}/")



def get_tags(html_content):
    """
    Extracts and returns all tags and 'comment' for HTML comments from an HTML content.

    :param html_content: HTML content as a string.
    :return: list of tags and 'comment' strings.
    """
    parser = EnhancedTagExtractor()
    parser.feed(html_content)
    return parser.tags

def structural_similarity(document_1, document_2):
    """
    Computes the structural similarity between two DOM Trees
    :param document_1: HTML content as a string
    :param document_2: HTML content as a string
    :return: float ratio indicating similarity
    """


    tags1 = get_tags(document_1)
    print("TAGS 1")
    print(tags1)
    input("wait")
    tags2 = get_tags(document_2)
    print("TAGS 2")
    print(tags2)
    input("wait")
    diff = difflib.SequenceMatcher(None, tags1, tags2)
    return diff.ratio()

def page_similarity(document_1, document_2):
    structural_sim = structural_similarity(document_1, document_2)
    style_sim = style_similarity(document_1, document_2)
    print(f"Structural sim {structural_sim}")
    print(f"Style sim {style_sim}")
    return min(structural_sim, style_sim)


url1 = "https://www.amazon.com/REDCON1-Noise-Non-Stim-Preworkout-Watermelon/dp/B08J8BW6KK?ref_=Oct_d_Oct_d_ss_d_6973697011_3&pd_rd_w=bkHf0&content-id=amzn1.sym.73640810-3777-4ff9-82ce-9a53681daf43&pf_rd_p=73640810-3777-4ff9-82ce-9a53681daf43&pf_rd_r=M4F20W3CRMB01GM64PGJ&pd_rd_wg=qxvbl&pd_rd_r=2775b13c-e05a-4ddf-b9c9-b1caa951770b&pd_rd_i=B08J8BW6KK"
# url2 = "https://www.amazon.com/gp/product/B077TWXCQV/ref=ewc_pr_img_1?smid=ATVPDKIKX0DER&psc=1"
url2 = "https://www.amazon.com/gp/product/B002RI97SO?storeType=ebooks&pf_rd_p=114af915-8ac1-4c2e-b2e9-571a645b5906&pf_rd_r=DBVN5590VZV5SS9SEPJ5&pd_rd_wg=NzgDm&pd_rd_i=B002RI97SO&ref_=dbs_f_def_rwt_wigo_cp_recs_wigo_4&pd_rd_w=9tDLW&content-id=amzn1.sym.114af915-8ac1-4c2e-b2e9-571a645b5906&pd_rd_r=037dccd2-8ed5-4fdb-8173-b32710ca17db"
# url2 = "https://www.amazon.com/live?ref_=nav_cs_amazonlive"
# url2 = "https://www.amazon.com/Brita-Replacement-BPA-Free-Replaces-Essential/dp/B082TJ4BP6?pd_rd_w=ZNrTH&content-id=amzn1.sym.80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_p=80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_r=04W3NQN7GAKTMN98KCK4&pd_rd_wg=jjnCM&pd_rd_r=2bad8d94-1c69-4a13-ad5f-77ded14e3bee&pd_rd_i=B082TJ4BP6&psc=1&ref_=pd_bap_d_grid_rp_0_10_i"
# url2 = "https://www.amazon.com/Optimum-Nutrition-Micronized-Monohydrate-Unflavored/dp/B002DYIZEO?pd_rd_w=ZNrTH&content-id=amzn1.sym.80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_p=80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_r=04W3NQN7GAKTMN98KCK4&pd_rd_wg=jjnCM&pd_rd_r=2bad8d94-1c69-4a13-ad5f-77ded14e3bee&pd_rd_i=B002DYIZEO&psc=1&ref_=pd_bap_d_grid_rp_0_4_i"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(url1)
    input("wait for load")
    document_1 = page.content()

    page.goto(url2)
    input("wait for load")
    document_2 = page.content()

# with open('el1.json', 'r') as file:
#     data = json.load(file)
#     document_1 = data["my_string"]
#
# with open('el2.json', 'r') as file:
#     data = json.load(file)
#     document_2 = data["my_string"]

# GO OFF STRUCTURAL SIMILARITY

simm = page_similarity(document_1, document_2)
print("SIM")
print(simm)