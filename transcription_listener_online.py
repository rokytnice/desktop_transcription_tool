import sounddevice as sd
import soundfile as sf
import numpy as np
from pynput import keyboard
import requests
import base64
import wave
import os
import subprocess
import time
import logging
import json

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False
file_path = "audio_recording.wav"
audio_data = []
input_stream = None

samplerate = 16000

# Logger erstellen
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Ausgabe in eine Datei
file_handler = logging.FileHandler('transcription_listener.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Ausgabe in die Konsole
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)


def start_recording():
    global recording, audio_data, input_stream
    if not recording:
        logger.info("Recording started...")
        recording = True
        audio_data = []
        input_stream = sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', callback=audio_callback)
        input_stream.start()


def stop_recording():
    global recording, input_stream
    if recording:
        logger.info("Recording stopped. Saving file...")
        recording = False
        input_stream.stop()
        input_stream.close()
        save_audio()
        transcribe_and_output()


def audio_callback(indata, frames, time, status):
    if recording:
        audio_data.append(indata.copy())


def save_audio():
    global audio_data
    try:
        if len(audio_data) == 0:
            logger.warning("No audio data to save.")
            return

        audio_array = np.concatenate(audio_data, axis=0)
        sf.write(file_path, audio_array, samplerate=samplerate, subtype='PCM_16')
        logger.info(f"Audio saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving audio: {e}")


def transcribe_audio(audio_file_path, api_key):
    with wave.open(audio_file_path, 'rb') as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        framerate = wav_file.getframerate()

        logger.info(f"Audio Properties - Channels: {channels}, Sample Width: {sample_width}, Framerate: {framerate}")

        if channels != 1 or sample_width != 2 or framerate != samplerate:
            logger.error("Invalid WAV file format.")
            raise ValueError("Invalid WAV file format.")

        audio_data = wav_file.readframes(wav_file.getnframes())
        if not audio_data:
            logger.info("No audio data to process.")
            return ""

    audio_content = base64.b64encode(audio_data).decode('utf-8')
    url = "https://speech.googleapis.com/v1/speech:recognize"

    request_data = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "de-DE",
            "enable_automatic_punctuation": True,
        },
        "audio": {
            "content": audio_content
        }
    }

    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(f"{url}?key={api_key}", json=request_data, headers=headers, timeout=10)
        response.raise_for_status()

        # Logge den gesamten Body der Antwort
        logger.debug(f"Response Body: {json.dumps(response.json(), indent=2)}")

    except requests.RequestException as e:
        logger.error(f"Failed to transcribe audio: {e}")
        raise

    response_data = response.json()
    transcription = "".join([result["alternatives"][0]["transcript"] for result in response_data.get("results",
                                                                                                     [])]) if "results" in response_data else "No transcription found."
    logger.info(f"Transcription result: {transcription}")
    return transcription


def type_text_in_active_window(text):
    time.sleep(0.5)
    try:
        for char in text:
            if ord(char) > 127:
                subprocess.run(["xdotool", "key", f"U{ord(char):04x}"], check=True)
            else:
                subprocess.run(["xdotool", "type", char], check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error typing text: {e}")


def transcribe_and_output():
    api_key = os.getenv("API_KEY")
    if not api_key:
        logger.error("API_KEY environment variable is not set.")
        return

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        logger.warning("Audio file is empty or does not exist. No content to process.")
        return

    try:
        transcription = transcribe_audio(file_path, api_key)
        logger.info("Transcription:")
        logger.info(transcription)

        if transcription:
            type_text_in_active_window(transcription)
        else:
            logger.warning("No transcription generated.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


def on_press(key):
    global current_keys
    current_keys.add(key)
    if keyboard.Key.ctrl_l in current_keys and keyboard.Key.alt_l in current_keys and keyboard.Key.insert in current_keys:
        start_recording()


def on_release(key):
    global current_keys
    if key in current_keys:
        current_keys.remove(key)
    if keyboard.Key.ctrl_l not in current_keys and keyboard.Key.alt_l not in current_keys and keyboard.Key.insert not in current_keys:
        stop_recording()


current_keys = set()

if __name__ == "__main__":
    logger.info("Hold Ctrl + Alt + Einfg to start recording. Release to stop recording and transcribe.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
