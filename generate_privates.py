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
    def __init__(self, url, private, public, acc_tree, embedding=None, parent=None, children=None):
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


def interpret_functionality_TREE_v7(tree_str, url, examples):
    messages = [
        {"role": "system",
         "content": "You are tasked with analyzing a web page based on its accessibility tree and URL. Your goal is to identify specific functionalities that are unique to the page, emphasizing the types of items or services it offers."},
        {"role": "system",
         "content": "Focus on functionalities that allow users to interact with the page's unique content, such as specific product categories or special services offered. Exclude generic functionalities or actions related to external links."},
        {"role": "system",
         "content": "Provide a concise analysis using action-oriented statements. Mention specific categories, types of products, or services that the page is centered around."},
        {"role": "system",
         "content": "Your response should be a Python-style list of brief action statements as strings, each highlighting a unique feature or functionality of the webpage, as indicated by the accessibility tree."},
        {"role": "system",
         "content": "Ensure that each action statement reflects the specific nature or theme of the webpage, providing insight into the type of user experience it offers."},
        {"role": "system",
         "content": "Here are a few examples of what your response should look like given their inputs:\n"}
    ]

    for example in examples:
        example_message = {
            "role": "user",
            "content": f"Example:\nAccessibility Tree: '{example['tree']}'\nURL: {example['url']}\nResponse: {example['response']}"
        }
        messages.append(example_message)

    # Add the actual query
    query_message = {
        "role": "user",
        "content": f"Analyze and list the specific and unique functionalities of this web page based on its accessibility tree and URL:\n{tree_str}\nURL: {url}\n"
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
     "response": "['Browse and purchase various Fan Shop items in the Sports & Outdoors category', 'Search for products using a basic or advanced search feature', 'Add products to Cart, Wish List, or Compare them', 'Filter and sort products by category, name, price, or position']"},
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


root_node = load_tree_from_file('webpage_tree_v2.json')

def generate_description_for_node(node):
    description = interpret_functionality_TREE_v7(node.acc_tree, node.url, few_shots)
    node.private = description
    print(f"URL: {node.url}\nDescription: {description}\n")

    for child in node.children:
        generate_description_for_node(child)
def serialize_tree(root_node):
    return root_node.to_dict()



tree_data = serialize_tree(root_node)
with open('webpage_tree_withprivates.json', 'w', encoding='utf-8') as file:
    json.dump(tree_data, file, ensure_ascii=False, indent=4)

