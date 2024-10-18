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

# Agents management: key -> {'agent': Agent, 'agent_task': Task, 'background_task': Task}
agents = {}
agents_lock = asyncio.Lock()

# Mapping of client session IDs to keys
client_keys = {}

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
        await sio.emit('connection_response', {'status': 'connected'}, to=sid)
        async with agents_lock:
            if key in agents:
                await sio.emit('agent_started', {'status': 'Agent already running'}, to=sid)

@sio.event
async def disconnect(sid):
    key = client_keys.pop(sid, None)
    if key:
        await sio.leave_room(sid, key)

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
                'agent': agent
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
            agent = agent_info['agent']
            await agent.input_queue.put(response)
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
                await sio.emit('browser_update', {'screenshot': data}, to=key)
            elif output_type == 'question':
                await sio.emit('agent_question', {'question': data}, to=key)
            elif output_type == 'only_out':
                await sio.emit('agent_only_out', {'message': data}, to=key)
        await asyncio.sleep(0.1)