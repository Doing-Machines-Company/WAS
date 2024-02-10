from memgpt import MemGPT
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
