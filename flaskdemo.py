from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from UIAgent import Agent
from threading import Thread, Lock

app = Flask(__name__)
socketio = SocketIO(app)

agent = Agent()
agent_initialized = False
agent_lock = Lock()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('connection_response', {'status': 'connected'})

@socketio.on('start_agent')
def handle_start_agent():
    global agent_initialized
    with agent_lock:
        if not agent_initialized:
            Thread(target=run_agent).start()
            agent_initialized = True
    emit('agent_started', {'status': 'Agent started'})

def run_agent():
    try:
        agent.run()
    finally:
        socketio.emit('agent_stopped')  # Emit when the agent stops, even if there's an error
def agent_loop():
    while True:
        if not agent.output_queue.empty():
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
    response = data['response']
    agent.input_queue.put(response)

if __name__ == '__main__':
    socketio.start_background_task(agent_loop)
    socketio.run(app, debug=True)