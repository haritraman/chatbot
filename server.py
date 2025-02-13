import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, send

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")  # Enable WebSocket

@app.route("/")
def index():
    return render_template("index.html")  # Serve the chat UI

@socketio.on("message")
def handle_message(msg):
    print(f"Received message: {msg}")
    send(msg, broadcast=True)  # Broadcast to all users

if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5001, debug=True)
