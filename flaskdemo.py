import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from UIAgent import Agent
from eventlet.green.threading import Thread, Lock
import time
import asyncio

app = Flask(__name__)
socketio = SocketIO(app)

agent: Agent = None
agent_thread = None
agent_lock = Lock()  # Initialize a lock
background_task_started = False  # Add this global variable

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global background_task_started
    emit('connection_response', {'status': 'connected'})
    if not background_task_started:
        socketio.start_background_task(agent_loop)
        background_task_started = True

@socketio.on('start_agent')
def handle_start_agent():
    global agent, agent_thread
    with agent_lock:  # Acquire the lock before checking/creating the agent
        if agent is None:
            agent = Agent()
            agent_thread = Thread(target=run_agent)
            agent_thread.start()
            emit('agent_started', {'status': 'Agent started'})
        else:
            emit('agent_already_running', {'status': 'Agent is already running'})

@socketio.on('reset_agent')
def handle_reset_agent():
    global agent, agent_thread
    with agent_lock:  # Ensure thread-safe reset
        if agent:
            print(f"{time.time()}: Stopping agent...")
            agent.stop()
            if agent_thread:
                start_time = time.time()
                agent_thread.join(timeout=20)  # Increased timeout to 20 seconds for better cleanup
                elapsed = time.time() - start_time
                print(f"{time.time()}: Join completed, took {elapsed:.2f} seconds")
                if agent_thread.is_alive():
                    print(f"{time.time()}: Warning: Agent thread did not stop within timeout.")
                else:
                    print(f"{time.time()}: Agent thread has successfully stopped.")
        agent = None
        agent_thread = None
        print(f"{time.time()}: Agent reset completed.")
        emit('agent_reset', {'status': 'Agent reset'})

def run_agent():
    global agent, agent_thread
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(agent.run())
    except Exception as e:
        print(f"{time.time()}: Agent encountered an error: {e}")
    finally:
        print(f"{time.time()}: Agent run method finished")
        socketio.emit('agent_stopped')
        print(f"{time.time()}: Agent thread finished")
        # Do NOT set agent and agent_thread to None here

def agent_loop():
    global agent
    while True:
        if agent and not agent.output_queue.empty():
            output_type, data = agent.output_queue.get()
            if output_type == 'screenshot':
                socketio.emit('browser_update', {'screenshot': data})
            elif output_type == 'question':
                socketio.emit('agent_question', {'question': data})
            elif output_type == 'only_out':
                socketio.emit('agent_only_out', {'message': data})
        socketio.sleep(0.1)


@socketio.on('user_response')
def handle_user_response(data):
    global agent
    response = data['response']
    if agent:
        agent.input_queue.put(response)

if __name__ == '__main__':
    socketio.run(app)
