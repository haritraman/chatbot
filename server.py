import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, send
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "uploads"

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
socketio = SocketIO(app, cors_allowed_origins="*")

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
    print(f"Received message: {data['username']}: {data['message']}")
    socketio.emit("message", {"username": data["username"], "message": data["message"]}, broadcast=True)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

