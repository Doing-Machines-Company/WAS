from memgpt import MemGPT
import re
with open('prompt1.txt', 'r') as file:
    my_message = file.read()
# Create a MemGPT client object (sets up the persistent state)
client = MemGPT(
  quickstart="openai",
  config={
    "openai_api_key": "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"
  }
)

# You can set many more parameters, this is just a basic example
agent_id = client.create_agent(
  agent_config={
    "name" : "WebAgentv3",
    "preset" : "agent_preset",
    "persona": "web_agent",
    "human": "basic",
  }
)
print(agent_id)

# Now that we have an agent_name identifier, we can send it a message!
# The response will have data from the MemGPT agent
response = client.user_message(agent_id=agent_id.id, message=my_message)
print(response)
for r in response:
    if "assistant_message" in r:
        result  = r["assistant_message"]
print(f"NEXT ACTION RAW: {result}")
result += 'HOLY SHIT THIS IS INSANE'
pattern = r'^\d+:(?:\s*\S.*)?$'

# Searching the LLM output for the pattern
match = re.findall(pattern, result)[0]
task_number, input_string = match.split(":")
print("T: ", task_number)
print("I:", input_string)