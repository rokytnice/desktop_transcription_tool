import threading
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

recording = False
file_path = "audio_recording.wav"
audio_data = []
input_stream = None

def start_recording():
    global recording, audio_data, input_stream
    if not recording:
        print("Recording started...")
        recording = True
        audio_data = []
        input_stream = sd.InputStream(samplerate=16000, channels=1, dtype='int16', callback=audio_callback)
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
        sf.write(file_path, audio_array, samplerate=16000, subtype='PCM_16')
        print(f"Audio saved to {file_path}")
    except Exception as e:
        print(f"Error saving audio: {e}")

def on_press(key):
    try:
        # Check for the specific key combination
        if (key == keyboard.KeyCode.from_char('r') and
            keyboard.Controller().alt_gr_pressed and
            keyboard.Controller().ctrl_pressed):
            if recording:
                stop_recording()
            else:
                start_recording()
    except Exception as e:
        print(f"Error: {e}")

def transcribe_audio(audio_file_path, api_key):
    with wave.open(audio_file_path, 'rb') as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2 or wav_file.getframerate() != 16000:
            raise ValueError("Invalid WAV file format.")

        audio_data = wav_file.readframes(wav_file.getnframes())

    audio_content = base64.b64encode(audio_data).decode('utf-8')
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
    request_data = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": "de-DE"
        },
        "audio": {
            "content": audio_content
        }
    }

    response = requests.post(url, json=request_data)
    if response.status_code != 200:
        raise Exception("Failed to transcribe audio.")

    response_data = response.json()
    return "".join([result["alternatives"][0]["transcript"] for result in response_data["results"]]) if "results" in response_data else "No transcription found."

def type_text_in_active_window(text):
    time.sleep(0.5)
    subprocess.run(["xdotool", "type", text], check=True)
    subprocess.run(["xdotool", "key", "Return"], check=True)

def transcribe_and_output():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY environment variable is not set.")
        return

    try:
        transcription = transcribe_audio(file_path, api_key)
        print("Transcription:")
        print(transcription)
        type_text_in_active_window(transcription)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    print("Press Ctrl + AltGr + R to start or stop recording.")
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()