import threading
import sounddevice as sd
import soundfile as sf
import numpy as np
from pynput import keyboard

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
    global recording
    try:
        if key == keyboard.Key.f5:
            if recording:
                stop_recording()
            else:
                start_recording()
        elif key == keyboard.Key.esc:
            if recording:
                stop_recording()
            print("Exiting program.")
            return False
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Press F5 to start or stop recording. Press Esc to exit.")
    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
