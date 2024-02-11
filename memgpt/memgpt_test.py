from memgpt import MemGPT
import re
import os
import time
with open('prompt1.txt', 'r') as file:
    my_message = file.read()
with open('prompt2.txt', 'r') as file:
    message2 = file.read()
# Create a MemGPT client object (sets up the persistent state)
client = MemGPT(
            # quickstart="openai",
            # config={
            #     "model": "gpt-3.5-turbo"
            # }
        )

# You can set many more parameters, this is just a basic example
agent_id = client.create_agent(
agent_config={
    "name" : "WebAgentv4",
    "preset" : "archive_preset",
    "persona": "archive_agent",
    "human": "basic",
    "model": "gpt-3.5-turbo-0125"
}
)

# Now that we have an agent_name identifier, we can send it a message!
# The response will have data from the MemGPT agent
print(agent_id.id)
response = client.user_message(agent_id=agent_id.id, message=my_message)
print(response)
response = client.user_message(agent_id=agent_id.id, message = message2)
print(response)

# for r in response:
#     if "assistant_message" in r:
#         result  = r["assistant_message"]
# print(f"NEXT ACTION RAW: {result}")
# result += 'HOLY SHIT THIS IS INSANE'
# pattern = r'^\d+:(?:\s*\S.*)?$'

# # Searching the LLM output for the pattern
# match = re.findall(pattern, result)[0]
# task_number, input_string = match.split(":")
# print("T: ", task_number)
# print("I:", input_string)
# os.system("echo y")
# os.system("memgpt delete-agent --agent-name WebAgentv3")
