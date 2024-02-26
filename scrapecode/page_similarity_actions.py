from html.parser import HTMLParser
from playwright.sync_api import sync_playwright


class ActionableElementExtractor(HTMLParser):
    """
    A custom HTML parser designed to extract actionable elements (like links, buttons,
    and form inputs) and their visible text or title attributes from an HTML document.
    """

    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in ['button', 'input', 'select', 'textarea']:
            self.current_tag = tag
            attrs_dict = dict(attrs)
            # For inputs and other self-closing tags, the visible text might be in their attributes (e.g., value, title, alt).
            # if 'value' in attrs_dict:
            #     print(attrs_dict['value'])
            #     text = attrs_dict['value']
            if 'title' in attrs_dict:
                text = attrs_dict['title']
            else:
                text = None
            self.elements.append((tag, text))

    def handle_endtag(self, tag):
        self.current_tag = None

    def handle_data(self, data):
        if self.current_tag in ['button']:
            # If the tag supports inner text, append it to the last element's text.
            if self.elements and self.elements[-1][0] == self.current_tag:
                tag, text = self.elements.pop()
                self.elements.append((tag, text + data.strip() if text else data.strip()))


def extract_actionable_elements(html_content):
    """
    Extracts actionable elements and their texts or titles from HTML content.

    :param html_content: HTML content as a string.
    :return: A list of tuples with actionable element tags and their texts or titles.
    """
    parser = ActionableElementExtractor()
    parser.feed(html_content)
    return parser.elements


def compare_actionable_elements(doc1, doc2):
    """
    Compares the actionable elements of two HTML documents to determine similarity.
    Elements must match in both type and visible text or title to be considered a match.

    :param doc1: HTML content of the first document as a string.
    :param doc2: HTML content of the second document as a string.
    :return: A float representing the similarity ratio between the documents.
    """
    elements1 = set(extract_actionable_elements(doc1))
    elements2 = set(extract_actionable_elements(doc2))

    intersection = len(elements1 & elements2)
    union = len(elements1 | elements2)
    similarity = intersection / union if union else 1
    return similarity


url1 = "https://www.amazon.com/REDCON1-Noise-Non-Stim-Preworkout-Watermelon/dp/B08J8BW6KK?ref_=Oct_d_Oct_d_ss_d_6973697011_3&pd_rd_w=bkHf0&content-id=amzn1.sym.73640810-3777-4ff9-82ce-9a53681daf43&pf_rd_p=73640810-3777-4ff9-82ce-9a53681daf43&pf_rd_r=M4F20W3CRMB01GM64PGJ&pd_rd_wg=qxvbl&pd_rd_r=2775b13c-e05a-4ddf-b9c9-b1caa951770b&pd_rd_i=B08J8BW6KK"
# url2 = "https://www.amazon.com/gp/product/B002RI97SO?storeType=ebooks&pf_rd_p=114af915-8ac1-4c2e-b2e9-571a645b5906&pf_rd_r=DBVN5590VZV5SS9SEPJ5&pd_rd_wg=NzgDm&pd_rd_i=B002RI97SO&ref_=dbs_f_def_rwt_wigo_cp_recs_wigo_4&pd_rd_w=9tDLW&content-id=amzn1.sym.114af915-8ac1-4c2e-b2e9-571a645b5906&pd_rd_r=037dccd2-8ed5-4fdb-8173-b32710ca17db"
url2 = "https://www.amazon.com/Brita-Replacement-BPA-Free-Replaces-Essential/dp/B082TJ4BP6?pd_rd_w=ZNrTH&content-id=amzn1.sym.80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_p=80b2efcb-1985-4e3a-b8e5-050c8b58b7cf&pf_rd_r=04W3NQN7GAKTMN98KCK4&pd_rd_wg=jjnCM&pd_rd_r=2bad8d94-1c69-4a13-ad5f-77ded14e3bee&pd_rd_i=B082TJ4BP6&psc=1&ref_=pd_bap_d_grid_rp_0_10_i"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(url1)
    input("wait for load")
    document_1 = page.content()

    page.goto(url2)
    input("wait for load")
    document_2 = page.content()



simm = compare_actionable_elements(document_1, document_2)

print(simm)