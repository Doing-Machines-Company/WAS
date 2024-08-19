from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from UIAgent import Agent
from threading import Thread, Lock
import time

app = Flask(__name__)
socketio = SocketIO(app)

agent = None
agent_thread = None
agent_lock = Lock()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('connection_response', {'status': 'connected'})

@socketio.on('start_agent')
def handle_start_agent():
    global agent, agent_thread
    with agent_lock:
        if agent is None:
            agent = Agent()
            agent_thread = Thread(target=run_agent)
            agent_thread.start()
            print(f"{time.time()}: Agent thread started")
    emit('agent_started', {'status': 'Agent started'})

@socketio.on('reset_agent')
def handle_reset_agent():
    global agent, agent_thread
    with agent_lock:
        if agent:
            print(f"{time.time()}: Stopping agent...")
            agent.stop()
            if agent_thread:
                start_time = time.time()
                agent_thread.join(timeout=5)  # Increased timeout to 10 seconds
                print(f"{time.time()}: Join completed, took {time.time() - start_time:.2f} seconds")
                if agent_thread.is_alive():
                    print(f"{time.time()}: Warning: Agent thread did not stop, forcing termination.")
        agent = None
        agent_thread = None
        print(f"{time.time()}: Agent reset completed.")
    emit('agent_reset', {'status': 'Agent reset'})

def run_agent():
    global agent
    try:
        agent.run()
    except Exception as e:
        print(f"{time.time()}: Agent encountered an error: {e}")
    finally:
        print(f"{time.time()}: Agent run method finished")
        socketio.emit('agent_stopped')
        print(f"{time.time()}: Agent thread finished")

def agent_loop():
    global agent
    while True:
        # with agent_lock:
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
    with agent_lock:
        if agent:
            agent.input_queue.put(response)

if __name__ == '__main__':
    socketio.start_background_task(agent_loop)
    socketio.run(app, debug=True)