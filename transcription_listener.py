#!/usr/bin/env python3

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


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/transcription_listener.log',
    filemode='a'  # 'a' für Anhängen, 'w' für Überschreiben bei jedem Start
)


def start_recording():
    global recording, audio_data, input_stream
    if not recording:
        print("Recording started...")
        recording = True
        audio_data = []
        input_stream = sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', callback=audio_callback)
        input_stream.start()

def stop_recording():
    global recording, input_stream
    if recording:
        print("Recording stopped. Saving file...")
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
            print("No audio data to save.")
            return

        audio_array = np.concatenate(audio_data, axis=0)

        sf.write(file_path, audio_array, samplerate=samplerate, subtype='PCM_16')
        print(f"Audio saved to {file_path}")
    except Exception as e:
        print(f"Error saving audio: {e}")

def on_press(key):
    global current_keys
    current_keys.add(key)
    if keyboard.Key.ctrl_l in current_keys and keyboard.Key.alt_l in current_keys:
        start_recording()

def on_release(key):
    global current_keys
    if key in current_keys:
        current_keys.remove(key)
    if keyboard.Key.ctrl_l not in current_keys or keyboard.Key.alt_l not in current_keys:
        stop_recording()

current_keys = set()

def transcribe_audio(audio_file_path, api_key):
    with wave.open(audio_file_path, 'rb') as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2 or wav_file.getframerate() != samplerate:
            logging.error("Invalid WAV file format.")
            raise ValueError("Invalid WAV file format.")

        audio_data = wav_file.readframes(wav_file.getnframes())
        if not audio_data:
            logging.info("No audio data to process.")
            return ""

    audio_content = base64.b64encode(audio_data).decode('utf-8')
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
    request_data = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "de-DE",
            "enable_automatic_punctuation": "True",
        },
        "audio": {
            "content": audio_content
        }
    }

    try:
        response = requests.post(url, json=request_data, timeout=10)
        response.raise_for_status()  # This will raise an exception for HTTP errors
    except requests.RequestException as e:
        logging.error(f"Failed to transcribe audio: {e}")
        raise

    response_data = response.json()
    transcription = "".join([result["alternatives"][0]["transcript"] for result in response_data["results"]]) if "results" in response_data else "No transcription found."
    logging.info(f"Transcription result: {transcription}")
    return transcription

def type_text_in_active_window(text):
    time.sleep(0.5)  # Wartezeit für den Fokus auf das aktive Fenster
    try:
        for char in text:
            if ord(char) > 127:  # Nicht-ASCII-Zeichen
                subprocess.run(["xdotool", "key", f"U{ord(char):04x}"], check=True)
            else:
                subprocess.run(["xdotool", "type", char], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error typing text: {e}")


def transcribe_and_output():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY environment variable is not set.")
        return

    # Überprüfen, ob die Audiodatei existiert und nicht leer ist
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        logging.info("Audio file is empty or does not exist. Skipping transcription.")
        return

    try:
        transcription = transcribe_audio(file_path, api_key)

        # Wenn keine Transkription gefunden wurde, nichts ausgeben
        if not transcription or transcription.strip() == "No transcription found.":
            logging.info("No valid transcription generated. Skipping output.")
            return

        # Transkription ausgeben und ins aktive Fenster eingeben
        logging.info(f"Transcription: {transcription}")
        type_text_in_active_window(transcription)
    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}")


if __name__ == "__main__":
    print("Hold Ctrl + Alt to start recording. Release to stop recording and transcribe.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
