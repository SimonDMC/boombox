from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import subprocess
import threading
from werkzeug.utils import secure_filename
from datetime import datetime
from google.cloud import texttospeech

app = Flask(__name__)
CORS(app)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'src/gcloud_key.json'
client = texttospeech.TextToSpeechClient()

voice = texttospeech.VoiceSelectionParams(
    language_code="en-US",
    name='en-US-Standard-B'
)

audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.MP3,
)

# Define the upload folder for temporary file storage
UPLOAD_FOLDER = 'uploads/'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Define maximum file size (in bytes)
MAX_FILE_SIZE = 5 * 1024 * 1024

# Define maximum allowed duration in seconds
MAX_DURATION = 180

# Define terminate and exit password
PASSWORD = "Xutv3N7VBB"

# Global variable to track playback status
is_playing = False

last_file = None

def play_audio_file(file_path):
    """Function to play audio using ffplay asynchronously."""
    global is_playing
    global last_file
    try:
        is_playing = True
        last_file = file_path
        process = subprocess.Popen(['ffplay', '-autoexit', '-nodisp', file_path],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        process.communicate()  # Wait for the process to complete
    except Exception as e:
        print(f"Error starting ffplay: {e}")
    finally:
        is_playing = False  # Mark as not playing once the audio finishes

def get_audio_duration(file_path):
    """Use ffprobe to get the duration of an audio file in seconds."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        return float(result.stdout)
    except Exception as e:
        return None

def is_webm(input_path):
    result = subprocess.run(
            ['file', input_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
    return "WebM" in str(result.stdout)

def convert_webm_to_opus(input_path, output_path):
    """Convert WebM file to Opus format using FFmpeg."""
    try:
        subprocess.run(['ffmpeg', '-i', input_path, '-c:a', 'libopus', output_path],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting WebM to Opus: {e}")
        return False

@app.route('/')
def root():
    return 'hello from a raspberry pi in my room :3'

@app.route('/ping')
def ping():
    return 'OK'

@app.route('/play-audio', methods=['POST'])
def play_audio():
    global is_playing
    # Check if something is already playing
    if is_playing:
        return jsonify({"error": "Audio is currently playing"}), 403
    
    # Check if an audio file is present in the request
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    audio_file = request.files['file']

    # If no file is selected
    if audio_file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Check file size
    if request.content_length > MAX_FILE_SIZE:
        return jsonify({"error": "File exceeds the 5 MB size limit"}), 400

    # Save the file securely
    filename = secure_filename(datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    audio_file.save(file_path)

    if is_webm(file_path):
        if convert_webm_to_opus(file_path, file_path + ".ogg"):
            os.remove(file_path)
            file_path = file_path + ".ogg"
            print("converting to ogg")
        else:
            return jsonify({"error": "Failed to convert WebM to Opus"}), 500

    # Check audio duration
    duration = get_audio_duration(file_path)
    if duration is None:
        return jsonify({"error": "Could not determine audio duration"}), 500
    if duration > MAX_DURATION:
        return jsonify({"error": "Audio file exceeds the 3-minute duration limit"}), 400

    # Start playing the audio in a separate thread
    def play_thread():
        try:
            play_audio_file(file_path)
        except Exception as e:
            print(f"Failed to play audio: {str(e)}")
    
    try:
        thread = threading.Thread(target=play_thread, daemon=True)
        thread.start()

        # Return the response right after starting the thread
        return jsonify({"message": "Audio playing"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to play the audio: {str(e)}"}), 500
    
@app.route('/play-text', methods=['POST'])
def play_text():
    global is_playing
    # Check if something is already playing
    if is_playing:
        return jsonify({"error": "Audio is currently playing"}), 403
    
    data = request.get_json()

    if not data['message']:
        return jsonify({"error": "Missing message parameter"}), 400
    
    message = data['message']

    if len(message) > 280:
        return jsonify({"error": "Message is over 280 characters"}), 400
    
    synthesis_input = texttospeech.SynthesisInput(text=message)

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    file_path = "uploads/" + datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    with open(file_path, "wb") as out:
        out.write(response.audio_content)
    
    # Start playing the audio in a separate thread
    def play_thread():
        try:
            play_audio_file(file_path)
        except Exception as e:
            print(f"Failed to play audio: {str(e)}")
    
    try:
        thread = threading.Thread(target=play_thread, daemon=True)
        thread.start()

        # Return the response right after starting the thread
        return jsonify({"message": "Message playing"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to play the audio: {str(e)}"}), 500

@app.route('/terminate-' + PASSWORD)
def terminate():
    subprocess.run(['pkill', '-9', '-f', 'ffplay'])
    return "done!"

@app.route('/replay-' + PASSWORD)
def replay():
    subprocess.run(['pkill', '-9', '-f', 'ffplay'])
    play_audio_file(last_file)

@app.route('/shutdown-' + PASSWORD)
def shutdown():
    subprocess.run(['pkill', '-9', '-f', 'ffplay'])
    subprocess.run(['pkill', '-9', '-f', 'app.py'])

if __name__ == '__main__':
    app.run(debug=True)
