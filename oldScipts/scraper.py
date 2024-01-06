from urllib.parse import urlparse, urlunparse
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
import os
import json

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

def get_embedding(text, model="text-embedding-ada-002"):
   text = text.replace("\n", " ")
   return client.embeddings.create(input = [text], model=model).data[0].embedding

class WebPageNode:
    def __init__(self, url=None, private=None, public=None, acc_tree=None, embedding=None, parent=None, children=None):
        self.url = url
        self.private = private
        self.public = private if public is None else public
        self.parent = parent
        self.acc_tree = acc_tree
        self.children = children if children is not None else []
        self.page_embedding = embedding

    def add_child(self, child_node):
        child_node.parent = self  # Set this node as the parent of the child
        self.children.append(child_node)

    def to_dict(self):
        return {
            "url": self.url,
            "private": self.private,
            "public": self.public,
            "acc_tree": self.acc_tree,
            "vec_embedding": self.page_embedding,
            "children": [child.to_dict() for child in self.children]
        }

    def __str__(self):
        parent_url = self.parent.url if self.parent else 'None'
        children_urls = ', '.join([child.url for child in self.children])
        return (f"WebPageNode(URL: {self.url}, Private: {self.private}, "
                f"Public: {self.public}, Parent URL: {parent_url}, "
                f"Children URLs: [{children_urls}]")
def normalize_url(url):
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


start_url = 'http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770?#'


def filter_urls(url_list):
    filtered_urls = []

    for url in url_list:
        is_substring = False
        for other_url in url_list:
            if url != other_url and url in other_url:
                is_substring = True
                break

        if not is_substring:
            filtered_urls.append(url)

    return filtered_urls


def filter_shortest_urls(url_list):
    filtered_urls = url_list.copy()

    for url in url_list:
        for other_url in url_list:
            if url != other_url and other_url in url:
                # If the other_url is a substring of url, remove the superstring url
                if url in filtered_urls:
                    filtered_urls.remove(url)
                break

    return filtered_urls

def load_text_file_as_list(file_path):
    with open(file_path, 'r') as file:
        return file.read().splitlines()


def filter_shortest_urls(url_list):
    filtered_urls = url_list.copy()

    while True:
        to_remove = set()

        for url in filtered_urls:
            for other_url in filtered_urls:
                if url != other_url and other_url in url:
                    to_remove.add(url)

        if not to_remove:
            break

        filtered_urls = [url for url in filtered_urls if url not in to_remove]

    return filtered_urls


def filter_urls_getshort(url_list):
    original_html_status = {url: url.endswith('.html') for url in url_list}

    modified_urls = [url[:-5] if url.endswith('.html') else url for url in url_list]

    filtered_urls = modified_urls.copy()

    for url in modified_urls:
        for other_url in modified_urls:
            if url != other_url and other_url in url:
                if url in filtered_urls:
                    filtered_urls.remove(url)

    final_urls = []
    for url in filtered_urls:
        original_url = url + '.html' if original_html_status.get(url + '.html', False) else url
        final_urls.append(original_url)

    return final_urls



def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')


ll = load_text_file_as_list('missed_links_v3.txt')

def interpret_functionality_TREE_v1(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with analyzing web pages in-depth. Your primary task is to provide a detailed evaluation of the web page's specific purpose."},
            {"role": "system",
             "content": "You will be given a page's accessibility tree and a parsed url. This is a simplified representation of the webpage, providing key information."},
            {"role": "system",
             "content": "You are to provide very brief and very specific descriptions of all functionalities of a web page. Only describe what can be done on the page. Be specific about the page's functionality and purpose. Include different functionalities in different descriptions. Do not in any circumstance include navigational information. You have to include details specific to the page."},
            {"role": "system",
             "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "system",
             "content": "Keep descriptions as brief as possible. Keep your entire list as brief as possible. Be as specific as possible."},
            {"role": "user",
             "content": f"Describe what can be done on this web page based on this accessibility tree:\n{tree_str}\n This is the page's url: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v0(tree_str):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are an autonomous intelligent agent tasked with analyzing web pages in-depth. Your primary task is to provide a detailed evaluation of the web page's overall purpose."},
            {"role": "system",
             "content": "You will be given a page's accessibility tree. This is a simplified representation of the webpage, providing key information."},
            {"role": "system",
             "content": "You are to provide very brief and concise descriptions of all functionalities of a web page. Do not include any details about links or what other links may do or how actions are performed. Only describe what can be done on the page. Be specific about the page's functionality and purpose. Include different functionalities in different descriptions. Do not in any circumstance include navigational details, do not include details about functionality that require navigating to another link or page. Do include page specific details. "},
            {"role": "system",
             "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "user",
             "content": f"Describe what can be done on this web page based on this accessibility tree:\n{tree_str}\nAgain, include only what can be done on this page. Keep descriptions as brief as possible. Keep your entire list as brief as possible."}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v2(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with providing an in-depth analysis of web pages. Focus on identifying and describing unique and specific functionalities of the webpage."},
            {"role": "system",
             "content": "Analyze the page's accessibility tree and URL to determine its specific purpose, such as selling certain types of products, offering unique services, or presenting exclusive content."},
            {"role": "system",
             "content": "Provide brief, specific descriptions of all unique functionalities and features of the web page. Avoid generic or navigational details. For example, if it's an online store, specify the types of products sold or any unique shopping features."},
            {"role": "system",
             "content": "Your response should be a list of quoted descriptions in the format of a Python list of strings like this: \n ['Specific functionality 1', 'Unique feature 2']"},
            {"role": "system",
             "content": "Be concise yet detailed in your descriptions, focusing on what makes the page distinct. Keep your entire list as brief as possible. Keep descriptions brief as well."},
            {"role": "user",
             "content": f"Describe the unique functionalities and features of this web page based on this accessibility tree:\n{tree_str}\n This is the page's URL: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v4(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with providing an in-depth yet highly concise analysis of web pages, focusing solely on the page in question."},
            {"role": "system",
             "content": "Analyze the page's accessibility tree and a cleaned URL (cleaning involves removing the website's home name) to identify unique functionalities and features specific to this page. Exclude any details about content or functionalities that involve navigating to other pages or external links that are not an extension of the current url."},
            {"role": "system",
             "content": "Provide extremely brief descriptions, ideally no more than a short sentence or phrase for each functionality or feature. Avoid mentioning generic features common to most web pages."},
            {"role": "system",
             "content": "Your response should be in the format of a Python-style list of strings, as succinct as possible, like this: \n '['Functionality 1', 'Feature 2']'\n Aim for each description to be concise and directly related to the page's unique aspects."},
            {"role": "system",
             "content": "Focus on what makes the page distinct, avoiding any mention of standard navigational or common web features."},
            {"role": "user",
             "content": f"Based on this accessibility tree and URL, describe only the unique and specific functionalities or features of this web page:\n{tree_str}\n This is the page's URL: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v3(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with analyzing a web page to identify specific actions that a user can perform directly on the page, based on its accessibility tree and a cleaned URL."},
            {"role": "system",
             "content": "Exclude functionalities or features that involve navigating to other pages or external links. Focus only on unique actions available on the current page."},
            {"role": "system",
             "content": "Provide descriptions using verbs to represent actions (e.g., 'Browse products', 'Add to cart'). Each description should be a concise phrase."},
            {"role": "system",
             "content": "Format your response as a Python-style list of strings, like this: \n ['Action 1', 'Action 2']\n Ensure each item in the list is a direct, actionable feature of the page."},
            {"role": "system",
             "content": "Avoid generic or common web features. Concentrate on specific and unique actions that can be performed on the webpage as indicated by the accessibility tree and a cleaned URL."},
            {"role": "user",
             "content": f"Based on this accessibility tree and URL, list the unique and specific actions that a user can perform on this web page:\n{tree_str}\n This is the page's cleaned URL: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v5(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with analyzing a web page based on its accessibility tree and URL. Your goal is to identify specific, actionable functionalities available directly on the page."},
            {"role": "system",
             "content": "Focus on functionalities that users can perform on the page itself. Exclude any actions related to external links or navigation to other pages."},
            {"role": "system",
             "content": "Provide a concise, action-oriented analysis. Use verbs to describe actions users can perform (e.g., 'browse products', 'add to cart'). Avoid lengthy descriptions."},
            {"role": "system",
             "content": "Your response should be a Python list of brief action statements. Each statement should directly relate to an actionable feature of the webpage, as indicated by the accessibility tree."},
            {"role": "system",
             "content": "Do not include generic web functionalities like navigation, unless they are central to the page's unique purpose."},
            {"role": "user",
             "content": f"Analyze and list the specific functionalities of this web page based on its accessibility tree and URL:\n{tree_str}\nURL: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v6(tree_str, url):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system",
             "content": "You are tasked with analyzing a web page based on its accessibility tree and URL. Your goal is to identify specific functionalities that are unique to the page, emphasizing the types of items or services it offers."},
            {"role": "system",
             "content": "Focus on functionalities that allow users to interact with the page's unique content, such as specific product categories or special services offered. Exclude generic functionalities or actions related to external links."},
            {"role": "system",
             "content": "Provide a concise analysis using action-oriented statements. Mention specific categories, types of products, or services that the page is centered around (e.g., 'purchase sports and outdoors equipment', 'browse fan shop items')."},
            {"role": "system",
             "content": "Your response should be a Python list of brief action statements, each highlighting a unique feature or functionality of the webpage, as indicated by the accessibility tree."},
            {"role": "system",
             "content": "Ensure that each action statement reflects the specific nature or theme of the webpage, providing insight into the type of user experience it offers."},
            {"role": "user",
             "content": f"Analyze and list the specific and unique functionalities of this web page based on its accessibility tree and URL:\n{tree_str}\nURL: {url}\n"}
        ],
    temperature=0.0,
    max_tokens=200
    )
    return response.choices[0].message.content

def interpret_functionality_TREE_v7(tree_str, url, examples):
    messages = [
        {"role": "system",
         "content": "You are tasked with analyzing a web page based on its accessibility tree and URL. Your goal is to identify specific functionalities that are unique to the page, emphasizing the types of items or services it offers."},
        {"role": "system",
         "content": "Focus on functionalities that allow users to interact with the page's unique content, such as specific product categories or special services offered. Exclude generic functionalities or actions related to external links."},
        {"role": "system",
         "content": "Provide a concise analysis using action-oriented statements. Mention specific categories, types of products, or services that the page is centered around."},
        {"role": "system",
         "content": "Your response should be a Python list of brief action statements, each highlighting a unique feature or functionality of the webpage, as indicated by the accessibility tree."},
        {"role": "system",
         "content": "Ensure that each action statement reflects the specific nature or purpose of the webpage, providing insight into the type of user experience it offers. "},
        {"role": "system",
         "content": "You have to exclude information about page layout or display or style. You have to exclude information about the page's viewing experience. Keep your response as concise as possible, don't include information that don't conform to the requirements."},
        {"role": "system",
         "content": "Here are a few examples of what your response should look like given their inputs:\n"}
    ]

    for example in examples:

        example_message = {
            "role": "system",
            "name": "example_user",
            "content": f"Accessibility tree:\n{example['tree']}\nURL: {example['response']}\n"
        }
        messages.append(example_message)
        example_response = {
            "role": "system",
            "name": "example_assistant",
            "content": f"{example['response']}"
        }
        messages.append(example_response)

    # Add the actual query
    query_message = {
        "role": "user",
        "content": f"Accessibility tree:\n{tree_str}\nURL: {url}\n"
    }
    messages.append(query_message)

    # API call to OpenAI
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=messages,
        temperature=0.0,
        max_tokens=200
    )

    return response.choices[0].message.content


few_shots = [
    {"tree": "[WebArea] 'Fan Shop - Sports & Outdoors'\n\t[link] 'My Account'\n\t[link] 'My Wish List'\n\t[link] 'Sign In'\n\t[link] 'Create an Account'\n\t[link] 'Skip to Content'\n\t[link] 'store logo'\n\t[link] '\\ue611 My Cart'\n\t[text] '\\ue615'\n\t[text] 'Search'\n\t[combobox] '\\ue615 Search'\n\t[link] 'Advanced Search'\n\t[button] 'Search'\n\t[link] 'Beauty & Personal Care'\n\t[link] 'Sports & Outdoors'\n\t[link] 'Clothing, Shoes & Jewelry'\n\t[link] 'Home & Kitchen'\n\t[link] 'Office Products'\n\t[link] 'Tools & Home Improvement'\n\t[link] 'Health & Household'\n\t[link] 'Patio, Lawn & Garden'\n\t[link] 'Electronics'\n\t[link] 'Cell Phones & Accessories'\n\t[link] 'Video Games'\n\t[link] 'Grocery & Gourmet Food'\n\t[link] 'Home '\n\t[text] '\\ue608'\n\t[link] 'Sports & Outdoors '\n\t[text] '\\ue608'\n\t[text] 'Fan Shop'\n\t[generic] ''\n\t[heading] 'Fan Shop Items 1-12 of 338'\n\t[text] 'View as'\n\t[text] '\\ue60d'\n\t[text] 'Grid'\n\t[link] 'View as \\ue60b List'\n\t[text] 'Items '\n\t[text] '1'\n\t[text] '-'\n\t[text] '12'\n\t[text] ' of '\n\t[text] '338'\n\t[text] 'Sort By'\n\t[combobox] 'Sort By'\n\t\t[menuitem] 'Position'\n\t\t[menuitem] 'Product Name'\n\t\t[menuitem] 'Price'\n\t[link] '\\ue613 Set Descending Direction'\n\t[link] 'Image'\n\t[link] 'DkRgVNY Lace Spcling Lingerie Womens Sexy Hollow Out Underwear Bodysuit One Piece Snap Crotch Clubwear Teddy Bodysuit'\n\t[text] '$11.09'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Mens Cotton Dress Shirts Short Sleeve Button Down Summer Casual Roll Up Beach Hawaiian Hipster Tops Classic Poplin Shirt'\n\t[text] '$12.99'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Wedge Sandals for Women Dressy Summer,Womens Shiny Ankle Strap Platform Block Chunky High Heel Pumps Sandals for Party'\n\t[text] '$21.34'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] \"Vera Bradley Women's Collegiate Plush XL Throw Blanket (Multiple Teams Available)\"\n\t[text] '$75.78'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Short Sleeve Button Down Shirts for Men Big and Tall Casual Floral Print Lapel Collar Tops Summer Beach Hawaiian T-Shirt'\n\t[text] '$10.98'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] \"Custom Jersey Style St Patrick's Day T Shirts - Saint Pattys Tee & Irish Outfits\"\n\t[text] 'Rating:'\n\t[text] '\\ue605\\ue605\\ue605\\ue605\\ue605'\n\t[text] '\\ue605\\ue605\\ue605\\ue605\\ue605'\n\t[text] '82%'\n\t[link] '12 \\xa0Reviews'\n\t[text] '$19.95'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Officially Licensed NFL \"Prestige\" Plush Raschel Throw Blanket, 60\" x 80\"'\n\t[text] '$34.95'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] \"WoCoo Men's Trench Coat Notch Lapel Double Breasted Long Pea Coats Premium Wool Blend Full Length Overcoat Outwear\"\n\t[text] '$38.99'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Light Blue Simple Summer New Low Heels Slippers for Women Fashion Chunky Heels Pointed Toe Wine Glasses Sandals Comfortable Walking Shoes Ladies All-Match Sexy Party Shoes'\n\t[text] '$14.59'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'Christmas Sweatshirt for Women Trendy Reindeer Graphic Hoodie Crewneck Long Sleeve Shirt Fashion Pullovers Jumper Tops'\n\t[text] '$14.99'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] \"Tops for Women Dressy, Women's O Neck Colorful Tees Shirt Casual Comfy Blouses Summer Short Sleeve Tunic Tops\"\n\t[text] '$8.51'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[link] 'Image'\n\t[link] 'FABIURT Christmas Sweaters for Women Tops Dressy Classic Fit Long Sleeve Casual Tunic T Shirt Blouse Tops Pullover Tee'\n\t[text] '$8.36'\n\t[button] 'Add to Cart'\n\t[button] 'Add to Wish List'\n\t[button] 'Add to Compare'\n\t[text] 'Page'\n\t[text] \"You're currently reading page\"\n\t[text] '1'\n\t[link] 'Page 2'\n\t[link] 'Page 3'\n\t[link] 'Page 4'\n\t[link] 'Page 5'\n\t[link] '\\ue608 Page Next'\n\t[text] 'Show'\n\t[combobox] 'Show'\n\t\t[menuitem] '12'\n\t\t[menuitem] '24'\n\t\t[menuitem] '36'\n\t[text] 'per page'\n\t[text] 'Shop By'\n\t[heading] 'Shopping Options'\n\t[heading] 'Category'\n\t[link] 'Clothing( 241 item )'\n\t[link] 'Footwear( 58 item )'\n\t[heading] 'Price'\n\t[link] '$0.00 - $99.99( 335 item )'\n\t[link] '$100.00 and above( 3 item )'\n\t[heading] 'Compare Products'\n\t[text] 'You have no items to compare.'\n\t[heading] 'My Wish List'\n\t[text] 'You have no items in your wish list.'\n\t[text] '\\ue61d'\n\t[text] 'Sign Up for Our Newsletter:'\n\t[textbox] 'Sign Up for Our Newsletter:'\n\t[button] 'Subscribe'\n\t[link] 'Privacy and Cookie Policy'\n\t[link] 'Search Terms'\n\t[link] 'Advanced Search'\n\t[link] 'Orders and Returns'\n\t[link] 'Contact Us'\n\t[text] 'Copyright © 2013-present Magento, Inc. All rights reserved.'\n\t[text] 'Help Us Keep Magento Healthy'\n\t[text] ' '\n\t[link] 'Report All Bugs'\n",
     "url": "http://ec2-18-189-15-215.us-east-2.compute.amazonaws.com:7770/sports-outdoors/fan-shop.html",
     "response": "['Browse and purchase various Fan Shop items', 'Search for products using a basic or advanced search feature', 'Add products to Cart, Wish List, or Compare them', 'Filter and sort products by category, name, price, or position',  'Read customer reviews and ratings for selected fan shop products']"},
]


def deserialize_node(node_data, parent=None):
    # Recreate a WebPageNode from the dictionary data.
    node = WebPageNode(
        url=node_data["url"],
        private=node_data["private"],
        public=node_data["public"],
        acc_tree=node_data["acc_tree"],
        embedding=node_data.get("vec_embedding"),
        parent=parent
    )

    for child_data in node_data["children"]:
        child_node = deserialize_node(child_data, parent=node)
        node.add_child(child_node)

    return node

def load_tree_from_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        tree_data = json.load(file)
    return deserialize_node(tree_data)


def clean_url(url):

    # Parse the URL to extract components
    parsed_url = urlparse(url)

    # Extract the path component and remove the leading '/'
    cleaned_path = parsed_url.path[1:]

    # Remove '.html' if it exists
    if cleaned_path.endswith(".html"):
        cleaned_path = cleaned_path[:-5]

    return cleaned_path


def get_links_of_tree(tree):
    links = []
    def dfs(node):
        links.append(node.url)
        for child in node.children:
            dfs(child)

    dfs(tree)

    return links
def normalize_url(url):  # Very aggressive normalization
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme if parsed_url.scheme else 'http'
    netloc = parsed_url.netloc
    path = parsed_url.path.rstrip('/')  # Remove trailing slashes from the path
    # Ignoring the query and fragment
    normalized_url = urlunparse((scheme, netloc, path, '', '', ''))
    return normalized_url


old_tree = load_tree_from_file('webpage_tree.json')
old_tree_nodes = get_links_of_tree(old_tree)
print(len(old_tree_nodes))
print(len(set(old_tree_nodes)))

new_tree = load_tree_from_file('webpage_tree_v6.json')
new_tree_nodes = get_links_of_tree(new_tree)
print(len(new_tree_nodes))
print(len(set(new_tree_nodes)))

print(set(old_tree_nodes) - set(new_tree_nodes))
with open('missed_links_v10.txt', 'w') as file:
    for link in set(old_tree_nodes) - set(new_tree_nodes):
        file.write(link + '\n')


# t2 = root_node.children[15]

# tacc = root_node.children
# print(tacc[0].url)
# tacc = root_node.children[8]
# tacc = root_node.children[8].children[0]

# print(tacc.url)

# print(interpret_functionality_TREE_v7(tacc.acc_tree, tacc.url, few_shots))


# print("t2 HERE: \n")
# print(t2.url)
# print(interpret_functionality_TREE(t2.acc_tree))

# embed_product_1 = [get_embedding(product_1)]
# embed_product_2 = [get_embedding(product_2)]
# embed_office_prods = [get_embedding(office_prods)]


'''
print(f"Sanity, should be 1: {cosine_similarity(embed_product_1, embed_product_1)}")

print(f"Similarity between {product_1} and {product_2}: {cosine_similarity(embed_product_1, embed_product_2)}")
print(f"Similarity between {product_1} and {office_prods}: {cosine_similarity(embed_product_1, embed_office_prods)}")
print(f"Similarity between {product_2} and {office_prods}: {cosine_similarity(embed_product_2, embed_office_prods)}")
'''
