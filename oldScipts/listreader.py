from urllib.parse import urlparse, urlunparse

from openai import OpenAI
import os

api_key = os.getenv('OPENAI_API_KEY')

client = OpenAI(api_key=api_key)

def url_depth(url):
    parsed = urlparse(url)
    return parsed.path.count('/')
def load_text_file_as_list(file_path):
    with open(file_path, 'r') as file:
        unsortedl = file.read().splitlines()
        # print(len(unsortedl))
        sortedl = sorted(unsortedl)
        lengths = [url_depth(url) for url in sortedl]
        print(f'max depth: {max(lengths)}')
        print(f'min depth: {min(lengths)}')
        four_links = [url for url in sortedl if url_depth(url) == 4] # mostly about customer account stuff, also search term??? huh????
        three_links = [url for url in sortedl if url_depth(url) == 3]
        three_links.sort()
        two_links = [url for url in sortedl if url_depth(url) == 2]
        two_links.sort()
        one_links = [url for url in sortedl if url_depth(url) == 1]
        one_links.sort()
        print("FOUR LINKS")
        print(four_links)
        print("THREE LINKS")
        print(three_links)
        # print(two_links)
        # print(one_links)
        with open("depthfourlinks.txt", 'w') as file:
            for line in four_links:
                file.write(line + "\n")


load_text_file_as_list('missed_links.txt')


def interpret_functionality_HTML(tree_str):
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {"role": "system", "content": "You are an autonomous intelligent agent tasked with analyzing web pages in-depth. Your primary task is to provide a detailed evaluation of the web page's overall purpose."},
            {"role": "system", "content": "You will be given a page's HTML. "},
            {"role": "system", "content": "Tell me what can be done on this web page and only on this web page. Do not include any details about functionality that the webpage links to. Give your answer in the format of a python list of strings.."},
            {"role": "system", "content": "Give your answer in the format of quoted descriptions in a list format enclosed within square brackets, like this: \n ['Descrition here', 'another description here']"},
            {"role": "user", "content": f"Describe what can be done on this web page based on this HTML:\n{tree_str}\nDo not include any information about what it links to, only what can be done on this page. Provide an exhaustive list of functionalities, keeping descriptions brief."}
        ],
        temperature=0.0
    )
    return response.choices[0].message.content

def interpret_functionality_TREE(tree_str):
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

with open('outhtml.txt', 'r') as file:
    html = file.read()
    print("HTML:")
    #print(interpret_functionality_HTML(html))

with open('outtreev2.txt', 'r') as file:
    tree = file.read()
    print("TREE:")
    # print(interpret_functionality_TREE(tree))