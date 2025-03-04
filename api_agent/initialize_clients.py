# initialize_clients.py

import os
from cerebras.cloud.sdk import AsyncCerebras
from together import AsyncTogether
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
# import google.generativeai as genai
import google.generativeai as google_client


# Initialize Async Cerebras Client
cerebras_client = AsyncCerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

# Initialize Async Together Client
together_client = AsyncTogether(api_key=os.environ.get('TOGETHER_API_KEY'))

# Initialize Async OpenAI Client
openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Initialize Async Anthropic Client
anthropic_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

google_client.configure(api_key=os.environ.get("GOOGLE_API_KEY"))