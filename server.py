from dotenv import load_dotenv
load_dotenv()
import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO, join_room, leave_room
from werkzeug.utils import secure_filename
import google.generativeai as genai
import json
import time

UPLOAD_FOLDER = "uploads"
BOT_NAME = "AI Bot"
CHAT_HISTORY_FILE = "chat_history.json"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure Gemini API
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# --- In-memory storage for rooms ---
# Structure: {"room_name": "password"}
rooms = {}

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- Chat History Helpers ----------------
def load_chat_history():
    """Loads chat history from a JSON file.
    History is now a dictionary with room names as keys."""
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                history = json.load(f)
                # Ensure the public lobby always exists
                if "public" not in history:
                    history["public"] = []
                return history
            except json.JSONDecodeError:
                return {"public": []}
    return {"public": []}

def save_chat_history(chat_history):
    """Saves the entire chat history dictionary to the JSON file."""
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_history, f, ensure_ascii=False, indent=2)

chat_history = load_chat_history()

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return "No file part", 400
    
    file = request.files["file"]
    room = request.form.get("room", "public") # Get room from the form

    if file.filename == "":
        return "No selected file", 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Save file upload in the correct room's chat history
    message_data = {"username": "You", "message": filename, "type": "file"}
    if room not in chat_history:
        chat_history[room] = []
    chat_history[room].append(message_data)
    save_chat_history(chat_history)

    # Emit the message only to the specific room
    socketio.emit("message", message_data, room=room)
    return "File uploaded successfully", 200

@app.route("/files/<filename>")
def get_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/history")
def get_history():
    # Return history for a specific room, default to public
    room_name = request.args.get('room', 'public')
    return jsonify(chat_history.get(room_name, []))

# ---------------- SocketIO Event Handlers ----------------
@socketio.on("create_room")
def handle_create_room(data):
    room_name = data.get("room_name")
    password = data.get("password")

    if not room_name or not password:
        socketio.emit("room_error", {"error": "Room name and password are required."}, to=request.sid)
        return

    if room_name in rooms or room_name == "public":
        socketio.emit("room_error", {"error": f"Room '{room_name}' already exists or is a reserved name."}, to=request.sid)
    else:
        rooms[room_name] = password
        join_room(room_name)
        
        # Initialize chat history for the new room if it doesn't exist
        if room_name not in chat_history:
            chat_history[room_name] = []
        
        socketio.emit("room_created", {"room_name": room_name}, to=request.sid)
        print(f"Room '{room_name}' created by {request.sid}")


@socketio.on("join_room")
def handle_join_room(data):
    room_name = data.get("room_name")
    password = data.get("password")

    if room_name not in rooms:
        socketio.emit("room_error", {"error": f"Room '{room_name}' does not exist."}, to=request.sid)
    elif rooms.get(room_name) != password:
        socketio.emit("room_error", {"error": "Incorrect password."}, to=request.sid)
    else:
        join_room(room_name)
        socketio.emit("room_joined", {"room_name": room_name}, to=request.sid)
        print(f"User {request.sid} joined room '{room_name}'")

@socketio.on("connect")
def handle_connect():
    """When a new user connects, add them to the public lobby."""
    join_room("public")
    print(f"Client connected: {request.sid} and joined the 'public' room.")

    
@socketio.on("message")
def handle_message(data):
    if not isinstance(data, dict):
        print("Invalid message format received:", data)
        return

    username = data.get("username", "Unknown")
    message = data.get("message", "")
    room = data.get("room", "public") # Get the room for the message

    # Save user message to the correct room's history
    message_data = {"username": username, "message": message, "type": "user"}
    chat_history.get(room, []).append(message_data)
    save_chat_history(chat_history)
    
    # Emit message only to clients in the specified room
    socketio.emit("message", message_data, room=room)

    # AI Bot logic (replies only to the room it was called in)
    if message.lower().startswith("@bot"):
        user_query = message[len("@bot"):].strip()
        if not user_query:
            bot_reply = "Please type something after @bot."
        else:
            socketio.emit("typing", {"username": BOT_NAME}, room=room)
            try:
                model = genai.GenerativeModel("models/gemini-2.5-flash")
                response = model.generate_content(user_query)

                if hasattr(response, "text") and response.text:
                    bot_reply = response.text
                elif hasattr(response, "candidates") and response.candidates:
                    parts = response.candidates[0].content.parts
                    bot_reply = " ".join(p.text for p in parts if hasattr(p, "text"))
                else:
                    bot_reply = "⚠️ No valid response from Gemini."

            except Exception as e:
                bot_reply = f"Error: {str(e)}"
            
            time.sleep(1) # Small delay to show typing indicator

        bot_message_data = {"username": BOT_NAME, "message": bot_reply, "type": "bot"}
        chat_history.get(room, []).append(bot_message_data)
        save_chat_history(chat_history)
        
        # Emit bot's reply only to the correct room
        socketio.emit("message", bot_message_data, room=room)

# ---------------- Main ----------------
if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5001)