# from llama_index.llms import OpenAILike
# from langchain.llms import Together
import time

# with open('poopoo.txt', 'r') as file:
#     prompt = file.read()
# llm = OpenAILike(
#     model="mistralai/Mixtral-8x7B-Instruct-v0.1",
#     api_base="https://api.together.xyz/v1",
#     api_key="c2cdc8649db190ab135ab85fb3df9487d6facd2696c652d2de470e92baefbb6f",
#     is_chat_model=True,
#     is_function_calling_model=True,
#     temperature=0.0,
# )
# start = time.time()
# response = llm.complete(prompt)
# end = time.time()
# print(response)
# print("took", end - start)



# llm = Together(
#     model="mistralai/Mixtral-8x7B-Instruct-v0.1",
#     temperature=0.0,
#     max_tokens=500,
#     top_k=1,
#     together_api_key="c2cdc8649db190ab135ab85fb3df9487d6facd2696c652d2de470e92baefbb6f"
# )

# input_ = prompt 
# start = time.time()
# print(llm(input_))
# end = time.time()
# print("took", end - start)

# import requests

# url = "https://api.together.xyz/inference"

# payload = {
#     "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
#     "prompt": "<s>[INST]" + prompt + "[/INST]",
#     "max_tokens": 512,
#     "stop": ["</s>", "[/INST]"],
#     "temperature": 0,
#     "top_p": 0,
#     "top_k": 50,
#     "repetition_penalty": 1,
#     "n": 1
# }
# headers = {
#     "accept": "application/json",
#     "content-type": "application/json",
#     "Authorization": "Bearer c2cdc8649db190ab135ab85fb3df9487d6facd2696c652d2de470e92baefbb6f"
# }
# start = time.time()
# response = requests.post(url, json=payload, headers=headers)
# end = time.time()
# print(response.text)
# print("took", end - start)
# import google.generativeai as genai
# GOOGLE_API_KEY = 'AIzaSyBu8ecdjq4gzAGbT5Tk-bQm38S0WZikyDs'
# genai.configure(api_key=GOOGLE_API_KEY)
# model = genai.GenerativeModel('gemini-pro')
# # Generate the response
# with open('poopoo.txt', 'r') as file:
# #     prompt = file.read()
# response = model.generate_content(prompt)

# from llava.model.builder import load_pretrained_model
# from llava.mm_utils import get_model_name_from_path
# from llava.eval.run_llava import eval_model

# model_path = "liuhaotian/llava-v1.6-34b"

# tokenizer, model, image_processor, context_len = load_pretrained_model(
#     model_path=model_path,
#     model_base=None,
#     model_name=get_model_name_from_path(model_path)
# )

# import os

# # from groq import Groq
with open('poopoo.txt', 'r') as file:
    sys_prompt = file.read()
with open('poopoo1.txt', 'r') as file2:
    prompt = file2.read()

# client = Groq(
#     api_key=os.environ.get("GROQ_API_KEY"),
# )
# start = time.time()
# chat_completion = client.chat.completions.create(
#     messages=[
#         {
#             "role": "user",
#             "content": sys_prompt + prompt,
#         }
#     ],
#     model="mixtral-8x7b-32768",
# )
# #print(chat_completion.choices[0].message.content)\
# print("Took ", str(time.time() - start), 's')
# print(chat_completion.choices[0].message.content)
# import anthropic


# client = anthropic.Anthropic(
#     # defaults to os.environ.get("ANTHROPIC_API_KEY")
#     api_key="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",
# )
# start = time.time()
# message = client.messages.create(
#     model="claude-3-haiku-20240307",
#     max_tokens=4000,
#     temperature=0,
#     system=sys_prompt,
#     messages=[
#         {
#             "role": "user",
#             "content": [
#                 {
#                     "type": "text",
#                     "text": prompt
#                 }
#             ]
#         }
#     ]
# )
# print(message.content)
# print("Took: ", time.time() - start, " s")


import webql

session = webql.start_session("https://www.amazon.com/s?k=ice+cream&crid=36NTDZRSFAENL&sprefix=ice+cream%2Caps%2C85&ref=nb_sb_noss_1")

QUERY = """
{
    results {
        products[0] {
            product_name
            num_reviews
            price
            rating
            shipping_fee
        }
    }
}
"""

response = session.query(QUERY)

print(response.results.products)



# session.stop()

# from openai import OpenAI
# import time
# client = OpenAI(api_key="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")
# start = time.time()
# response = client.chat.completions.create(
#   model="gpt-4-turbo-2024-04-09",
#   messages=[
#     {
#       "role": "system",
#       "content": "You are an autonomous intelligent agent that is tasked with navigating a website. You will be given a user objective that you will help the user get one step closer by selecting one of the options from the accessibility tree. Each action is bracketed [], and corresponds to a single, atomic action that you must choose to help accomplish the user objective. You will be told where you are currently, and what the objective is, and from this, you must return the number that most likely corresponds to the correct action. \n\n ***IMPORTANT: DON'T EXPLAIN YOUR THINKING. ONLY RETURN THE NUMBER [#]. I REPEAT, ONLY RETURN THE NUMBER***"
#     },
#     {
#       "role": "user",
#       "content": prompt
#     },
#   ],
#   temperature=0,
#   max_tokens=4095,
#   top_p=1,
#   frequency_penalty=0,
#   presence_penalty=0
# )
# print(response)
# print("Took", time.time() - start, " seconds")