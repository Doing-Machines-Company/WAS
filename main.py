# main.py
import socketio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import asyncio
from UIAgent import Agent
import gc
import time
import os
from collections import defaultdict

# Initialize Socket.IO server with ASGI mode
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Set up templates directory
templates = Jinja2Templates(directory="templates")

# Define valid keys (replace with your actual keys or load from environment variables)
valid_keys = set(['key1', 'key2', 'key3'])  # Example keys
# Alternatively, load from an environment variable:
# valid_keys = set(k.strip() for k in os.getenv('VALID_KEYS', '').split(',') if k.strip())

# Agents management: key -> {
#     'agent': Agent,
#     'agent_task': Task,
#     'background_task': Task,
#     'messages': List[Dict],
#     'browserScreenshot': str,
#     'waiting_for_input': bool
# }
agents = {}
agents_lock = asyncio.Lock()

# Mapping of client session IDs to keys
client_keys = {}

# Mapping of keys to sets of connected sids
key_clients = defaultdict(set)

@app.get("/", response_class=HTMLResponse)
async def get(request: Request, key: str = None):
    if not key or key not in valid_keys:
        return templates.TemplateResponse("invalid_key.html", {"request": request})
    return templates.TemplateResponse("index.html", {"request": request, "key": key})

@sio.event
async def connect(sid, environ):
    # Extract key from query string
    query_string = environ.get('QUERY_STRING', '')
    key = None
    for param in query_string.split('&'):
        if param.startswith('key='):
            key = param.split('=')[1]
            break
    if not key or key not in valid_keys:
        await sio.emit('connection_response', {'status': 'invalid_key'}, to=sid)
        await sio.disconnect(sid)
    else:
        await sio.enter_room(sid, key)
        client_keys[sid] = key
        key_clients[key].add(sid)
        await sio.emit('connection_response', {'status': 'connected'}, to=sid)
        async with agents_lock:
            if key in agents:
                # Agent is already running
                await sio.emit('agent_started', {'status': 'Agent already running'}, to=sid)
                # Send the current state to the newly connected client
                await sio.emit('agent_state', {
                    'messages': agents[key]['messages'],
                    'browserScreenshot': agents[key]['browserScreenshot'],
                    'waiting_for_input': agents[key]['waiting_for_input']
                }, to=sid)
            else:
                # Optionally, start the agent automatically upon first connection
                # Uncomment the following lines if you want to auto-start agents
                # agent = Agent()
                # agents[key] = {
                #     'agent': agent,
                #     'messages': [],
                #     'browserScreenshot': '',
                #     'waiting_for_input': False
                # }
                # agent_task = asyncio.create_task(run_agent(key))
                # background_task = asyncio.create_task(agent_loop(key))
                # agents[key]['agent_task'] = agent_task
                # agents[key]['background_task'] = background_task
                pass

@sio.event
async def disconnect(sid):
    key = client_keys.pop(sid, None)
    if key:
        await sio.leave_room(sid, key)
        key_clients[key].discard(sid)
        if not key_clients[key]:
            # No more clients connected to this key, reset the agent
            async with agents_lock:
                agent_info = agents.get(key)
                if agent_info:
                    agent = agent_info['agent']
                    print(f"{time.time()}: Stopping agent for key {key} due to no active connections...")
                    if agent and not agent.cleaned_up.is_set():
                        agent.stop()
                        try:
                            await asyncio.wait_for(agent.cleaned_up.wait(), timeout=20)
                            print(f"{time.time()}: Agent for key {key} cleanup completed.")
                        except asyncio.TimeoutError:
                            print(f"{time.time()}: Warning: Agent for key {key} did not clean up within timeout.")
                    # Cancel the agent task
                    agent_task = agent_info.get('agent_task')
                    if agent_task:
                        agent_task.cancel()
                        try:
                            await agent_task
                        except asyncio.CancelledError:
                            pass
                    # Cancel the background task
                    background_task = agent_info.get('background_task')
                    if background_task:
                        background_task.cancel()
                        try:
                            await background_task
                        except asyncio.CancelledError:
                            pass
                    # Clear the agent's state
                    del agents[key]
                    gc.collect()
                    print(f"{time.time()}: Agent reset completed for key {key} due to no active connections.")
                    await sio.emit('agent_reset', {'status': 'Agent reset due to no active connections'}, to=key)

@sio.event
async def start_agent(sid):
    key = client_keys.get(sid)
    if not key:
        await sio.emit('error', {'message': 'No key associated with this connection'}, to=sid)
        return
    async with agents_lock:
        if key not in agents:
            agent = Agent()
            agents[key] = {
                'agent': agent,
                'messages': [],
                'browserScreenshot': '',
                'waiting_for_input': False
            }
            # Start the agent's run method as a background task
            agent_task = asyncio.create_task(run_agent(key))
            # Start the background loop to handle agent outputs
            background_task = asyncio.create_task(agent_loop(key))
            agents[key]['agent_task'] = agent_task
            agents[key]['background_task'] = background_task
            await sio.emit('agent_started', {'status': 'Agent started'}, to=key)
        else:
            await sio.emit('agent_already_running', {'status': 'Agent is already running'}, to=sid)

@sio.event
async def reset_agent(sid):
    key = client_keys.get(sid)
    if not key:
        await sio.emit('error', {'message': 'No key associated with this connection'}, to=sid)
        return
    async with agents_lock:
        agent_info = agents.get(key)
        if agent_info:
            agent = agent_info['agent']
            print(f"{time.time()}: Stopping agent for key {key}...")
            if agent and not agent.cleaned_up.is_set():
                agent.stop()
                try:
                    await asyncio.wait_for(agent.cleaned_up.wait(), timeout=20)
                    print(f"{time.time()}: Agent for key {key} cleanup completed.")
                except asyncio.TimeoutError:
                    print(f"{time.time()}: Warning: Agent for key {key} did not clean up within timeout.")
            # Cancel the agent task
            agent_task = agent_info.get('agent_task')
            if agent_task:
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
            # Cancel the background task
            background_task = agent_info.get('background_task')
            if background_task:
                background_task.cancel()
                try:
                    await background_task
                except asyncio.CancelledError:
                    pass
            # Clear the agent's state
            agent_info['messages'].clear()
            agent_info['browserScreenshot'] = ''
            agent_info['waiting_for_input'] = False
            del agents[key]
            gc.collect()
            print(f"{time.time()}: Agent reset completed for key {key}.")
            await sio.emit('agent_reset', {'status': 'Agent reset'}, to=key)
        else:
            await sio.emit('error', {'message': 'No agent to reset for this key'}, to=sid)

@sio.event
async def user_response(sid, data):
    key = client_keys.get(sid)
    if not key:
        await sio.emit('error', {'message': 'No key associated with this connection'}, to=sid)
        return
    response = data.get('response')
    if not response:
        await sio.emit('error', {'message': 'No response provided'}, to=sid)
        return
    async with agents_lock:
        agent_info = agents.get(key)
        if agent_info:
            if not agent_info['waiting_for_input']:
                await sio.emit('error', {'message': 'Agent is not waiting for input'}, to=sid)
                return
            agent = agent_info['agent']
            # Append user message to the agent's message list
            agent_info['messages'].append({'type': 'user', 'text': response})
            agent_info['waiting_for_input'] = False
            await agent.input_queue.put(response)
            # Broadcast the user message to all clients in the key's room except sender
            await sio.emit('user_message', {'text': response}, to=key, skip_sid=sid)
            # Emit 'input_disabled' to all clients in the room to disable input fields
            await sio.emit('input_disabled', to=key)
        else:
            await sio.emit('error', {'message': 'Agent is not running'}, to=sid)

async def run_agent(key):
    agent_info = agents.get(key)
    if not agent_info:
        print(f"{time.time()}: No agent found for key {key}")
        return
    agent = agent_info['agent']
    try:
        await agent.run()
    except asyncio.CancelledError:
        print(f"{time.time()}: Agent for key {key} was cancelled.")
    except Exception as e:
        print(f"{time.time()}: Agent for key {key} encountered an error: {e}")
    finally:
        print(f"{time.time()}: Agent run method for key {key} finished")
        await sio.emit('agent_stopped', to=key)
        print(f"{time.time()}: Agent task for key {key} finished")

async def agent_loop(key):
    agent_info = agents.get(key)
    if not agent_info:
        return
    agent = agent_info['agent']
    while not agent.stop_event.is_set():
        if not agent.output_queue.empty():
            output_type, data = await agent.output_queue.get()
            if output_type == 'screenshot':
                agent_info['browserScreenshot'] = data  # Update the current screenshot
                await sio.emit('browser_update', {'screenshot': data}, to=key)
            elif output_type == 'question':
                message = {'type': 'agent', 'text': data}
                agent_info['messages'].append(message)  # Append agent question to messages
                agent_info['waiting_for_input'] = True
                await sio.emit('agent_question', {'question': data}, to=key)
            elif output_type == 'only_out':
                message = {'type': 'only-out', 'text': data}
                agent_info['messages'].append(message)  # Append agent-only message to messages
                await sio.emit('agent_only_out', {'message': data}, to=key)
        await asyncio.sleep(0.1)
