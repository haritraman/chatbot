from dotenv import load_dotenv
load_dotenv()
import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, send_from_directory, jsonify
from flask_socketio import SocketIO
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

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- Chat History Helpers ----------------
def load_chat_history():
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_chat_history(chat_history):
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
    if file.filename == "":
        return "No selected file", 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # Save file upload in chat history
    chat_history.append({"username": "You", "message": filename, "type": "file"})
    save_chat_history(chat_history)

    socketio.emit("message", {"username": "You", "message": filename, "type": "file"})
    return "File uploaded successfully", 200

@app.route("/files/<filename>")
def get_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/history")
def get_history():
    return jsonify(chat_history)

# ---------------- SocketIO ----------------
@socketio.on("message")
def handle_message(data):
    if not isinstance(data, dict):
        print("Invalid message format received:", data)
        return

    username = data.get("username", "Unknown")
    message = data.get("message", "")

    # Save user message
    chat_history.append({"username": username, "message": message, "type": "user"})
    save_chat_history(chat_history)
    socketio.emit("message", {"username": username, "message": message, "type": "user"})

    # AI Bot logic
    if message.lower().startswith("@bot"):
        user_query = message[len("@bot"):].strip()
        if not user_query:
            bot_reply = "Please type something after @bot."
            chat_history.append({"username": BOT_NAME, "message": bot_reply, "type": "bot"})
            save_chat_history(chat_history)
            socketio.emit("message", {"username": BOT_NAME, "message": bot_reply, "type": "bot"})
            return

        # Emit typing indicator
        socketio.emit("typing", {"username": BOT_NAME})

        try:
            model = genai.GenerativeModel("models/gemini-1.5-flash")
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

        # Small delay to show typing indicator
        time.sleep(1)

        # Save bot reply
        chat_history.append({"username": BOT_NAME, "message": bot_reply, "type": "bot"})
        save_chat_history(chat_history)

        socketio.emit("message", {"username": BOT_NAME, "message": bot_reply, "type": "bot"})

# ---------------- Main ----------------
if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5001)
