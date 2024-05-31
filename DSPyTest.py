import os
import dspy
from openai import OpenAI
from dspy.teleprompt import BootstrapFewShot

# Initialize the OpenAI client with GPT-4o
api_key = os.getenv('OPENAI_API_KEY')
openai_client = OpenAI(api_key=api_key)
teacher = dspy.OpenAI(model='gpt-4o', api_key=api_key, api_provider="openai", model_type="chat")

# Configure DSPy settings to use GPT-4o
dspy.settings.configure(lm=openai_client)

class HTMLInputGenerator(dspy.Module):
    def __init__(self):
        super().__init__()

    def forward(self, memory, website_info, outerHTML):
        # Define the messages
        messages = [
            {"role": "system", "content": "You are an AI assistant that generates example input strings for HTML elements. "},
            {"role": "user", "content": f"Given the memory: {memory}, website information: {website_info}, and outerHTML: {outerHTML}, give me ONLY the text that can be used to fill the input box."}
        ]

        # Call GPT-4o with the messages
        response = openai_client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            max_tokens=100,
            temperature=0
        )

        # Extract the input strings from the response
        # print(response.choices[0].message.content.strip())
        input_strings = response.choices[0].message.content.strip().split('\n')
        input_strings = [string.strip().replace('-', '').strip() for string in input_strings]
        return input_strings

# Example training data
train_data = [
    dspy.Example(memory="User preferences", website_info="E-commerce site", outerHTML="<input type='text' id='search'>", input_strings=["shoes", "shirts", "pants", "hats", "socks"]).with_inputs("memory", "website_info", "outerHTML"),
    dspy.Example(memory="User history", website_info="Blog site", outerHTML="<input type='text' id='comment'>", input_strings=["great post", "interesting", "thanks for sharing", "nice article", "good read"]).with_inputs("memory", "website_info", "outerHTML")
]

# Instantiate the module
html_input_generator_module = HTMLInputGenerator()

# Define the optimizer
config = dict(max_bootstrapped_demos=3)
optimizer = BootstrapFewShot(teacher_settings=dict({'lm': teacher}), **config)

# Optimize the model
optimized_module = optimizer.compile(student=html_input_generator_module, trainset=train_data)

# Evaluate the optimized model
dev_set = [
    dspy.Example(memory="User just had a bad day", website_info="Social media site", outerHTML="<input type='text' id='status'>", input_strings=["hello world", "feeling great", "good morning", "happy day", "excited"]).with_inputs("memory", "website_info", "outerHTML"),
    dspy.Example(memory="User wants a tennis racket", website_info="News site", outerHTML="<input type='text' id='search'>", input_strings=["latest news", "breaking news", "top stories", "headlines", "current events"]).with_inputs("memory", "website_info", "outerHTML")
]

# Print the results
for example in dev_set:
    baseline = html_input_generator_module.forward(example.memory, example.website_info, example.outerHTML)
    prediction = optimized_module.forward(example.memory, example.website_info, example.outerHTML)
    # print(f"Memory: {example.memory}")
    # print(f"Website Info: {example.website_info}")
    # print(f"Outer HTML: {example.outerHTML}")
    print(f"Prediction: {prediction}")
    print(f"Baseline: {baseline}")
    print()