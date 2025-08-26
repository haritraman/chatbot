from dotenv import load_dotenv
load_dotenv()
import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, send
from werkzeug.utils import secure_filename
import google.generativeai as genai

UPLOAD_FOLDER = "uploads"
BOT_NAME = "AI Bot"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure Gemini API
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

    socketio.emit("file_uploaded", filename)  # Notify clients about the uploaded file
    return "File uploaded successfully", 200

@app.route("/files/<filename>")
def get_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@socketio.on("message")
def handle_message(data):
    if not isinstance(data, dict):
        print("Invalid message format received:", data)
        return  # Ignore invalid messages

    username = data.get("username", "Unknown")
    message = data.get("message", "")

    print(f"Received message: {username}: {message}")
    socketio.emit("message", {"username": username, "message": message})

    # --- AI BOT LOGIC ---
    if message.lower().startswith("@bot"):
        print("@bot command detected. Processing AI response...")

        # ✅ Safely extract everything after "@bot"
        user_query = message[len("@bot"):].strip()
        print(f"User query for bot: {user_query}")

        if not user_query:
            bot_reply = "Please type something after @bot."
            socketio.emit("message", {"username": BOT_NAME, "message": bot_reply})
            return

        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            print("Gemini model created.")
            response = model.generate_content(user_query)

            # ✅ Safely extract text (Gemini sometimes returns candidates/parts)
            if hasattr(response, "text") and response.text:
                bot_reply = response.text
            elif hasattr(response, "candidates") and response.candidates:
                parts = response.candidates[0].content.parts
                bot_reply = " ".join(p.text for p in parts if hasattr(p, "text"))
            else:
                bot_reply = "⚠️ No valid response from Gemini."

        except Exception as e:
            print(f"Error from Gemini API: {e}")
            bot_reply = f"Error: {str(e)}"

        # Emit bot response back into chat
        print(f"Bot reply: {bot_reply}")
        socketio.emit("message", {"username": BOT_NAME, "message": bot_reply})


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5001)
