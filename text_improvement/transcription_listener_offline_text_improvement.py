#!/usr/bin/env python3

import sounddevice as sd
import soundfile as sf
import numpy as np
from pynput import keyboard
import os
import subprocess
import time
import logging
import whisper
import torch
import requests
import json

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False
file_path = "audio_recording.wav"
audio_data = []
input_stream = None

samplerate = 16000
GEMINI_API_KEY = "DEIN_GEMINI_API_KEY"  # Ersetze dies mit deinem echten API-Schlüssel

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

current_keys = set()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/transcription_listener.log',
    filemode='a'
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
    if keyboard.Key.ctrl_l in current_keys and keyboard.Key.alt_l in current_keys and keyboard.Key.insert in current_keys:
        start_recording()


def on_release(key):
    global current_keys
    if key in current_keys:
        current_keys.remove(key)
    if keyboard.Key.ctrl_l not in current_keys and keyboard.Key.alt_l not in current_keys and keyboard.Key.insert not in current_keys:
        stop_recording()


def transcribe_with_whisper(audio_file_path):
    try:
        model = whisper.load_model("base")
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        result = model.transcribe(audio_file_path, fp16=True, language="de", task="transcribe")

        transcription = result["text"]
        logging.info(f"Transcription result: {transcription}")

        return transcription
    except Exception as e:
        logging.error(f"Failed to transcribe audio with Whisper: {e}")
        raise


def enhance_text_with_llm(text):
    """Sendet den transkribierten Text an die Gemini API zur Verbesserung."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [{
                "parts": [{"text": f"Verbessere diesen Text in der gleichen Sprache: {text}"}]
            }]
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            response_data = response.json()
            improved_text = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if improved_text:
                logging.info(f"LLM-verbesserter Text: {improved_text}")
                return improved_text
        else:
            logging.error(f"Fehler beim Abruf der API: {response.status_code} - {response.text}")

    except Exception as e:
        logging.error(f"Fehler bei der Kommunikation mit der Gemini API: {e}")

    return text  # Falls Verbesserung fehlschlägt, Originaltext zurückgeben


def type_text_in_active_window(text):
    """Gibt den Text ins aktive Fenster ein."""
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
    """Führt die Transkription durch, schickt den Text an das LLM und gibt ihn aus."""
    try:
        print("Starting transcription...")
        logging.info("Starting transcription...")

        transcription = transcribe_with_whisper(file_path)

        if not transcription or transcription.strip() == "":
            print("No valid transcription found.")
            logging.info("No valid transcription generated.")
            return

        print(f"Raw transcription: {transcription}")
        logging.info(f"Raw transcription: {transcription}")

        # Text durch das LLM verbessern
        improved_text = enhance_text_with_llm(transcription)

        # Verbesserter Text ausgeben und in aktives Fenster schreiben
        print(f"Enhanced Transcription: {improved_text}")
        logging.info(f"Enhanced Transcription: {improved_text}")
        type_text_in_active_window(improved_text)

    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}")
        print(f"An error occurred during transcription: {e}")


if __name__ == "__main__":
    print("Hold Ctrl + Alt + Einfg to start recording. Release to stop recording and transcribe.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
