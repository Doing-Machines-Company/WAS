import requests

url = "http://localhost:8283/agents/message"

with open('poop.txt', 'r') as file:
    message = file.read()
payload = {
    "user_id": "cem",
    "agent_id": "agent_1",
    "message": message,
    "stream": False,
    "role": "user"
}
headers = {
    "accept": "application/json",
    "content-type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.text)

