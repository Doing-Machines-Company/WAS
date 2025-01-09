# initialize_clients.py

import os
import anthropic
from cerebras.cloud.sdk import Cerebras
from together import Together
from groq import Groq
from openai import OpenAI
import google.generativeai as google_client

# Initialize Anthropic Client
anthropic_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# Initialize Cerebras Client
cerebras_client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

# Initialize Together Client
together_client = Together(api_key=os.environ.get('TOGETHER_API_KEY'))

# Initialize Groq Client
groq_client = Groq()

# Initialize OpenAI Client
openai_client = OpenAI()

# Initialize Google Client
google_client.configure(api_key=os.environ.get("GOOGLE_API_KEY"))