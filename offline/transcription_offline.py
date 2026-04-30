#!/usr/bin/env python3

import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import subprocess
import time
import logging
import whisper
import torch
import evdev
from evdev import InputDevice, ecodes, list_devices
import threading

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False
file_path = "audio_recording.wav"
audio_data = []
input_stream = None

samplerate = 16000
device_index = None  # Will be selected at startup

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

# Audio device selection
def select_audio_device():
    """Show available audio input devices and let user select one"""
    global device_index

    print("\n=== AVAILABLE MICROPHONE DEVICES (Audio Input) ===\n")

    devices_list = []
    all_devices = sd.query_devices()

    for idx, device in enumerate(all_devices):
        if device['max_input_channels'] > 0:
            devices_list.append(idx)
            is_default = " ← DEFAULT" if idx == sd.default.device[0] else ""
            print(f"[{len(devices_list)-1}] Device #{idx}: {device['name']}{is_default}")
            print(f"         Channels: {device['max_input_channels']}, Rate: {device['default_samplerate']} Hz")

    print()
    if len(devices_list) == 0:
        raise RuntimeError("No audio input devices found!")

    if len(devices_list) == 1:
        device_index = devices_list[0]
        logger.info(f"Auto-selected device: {all_devices[device_index]['name']}")
        return device_index

    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}]: ").strip()
            choice_idx = int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            device_index = devices_list[choice_idx]
            selected_name = all_devices[device_index]['name']
            print(f"\n✓ Using: {selected_name}\n")
            logger.info(f"Selected device {device_index}: {selected_name}")
            return device_index
        except ValueError:
            print("Please enter a number!")

# Keyboard device detection
def find_keyboard_devices():
    devices = []
    for path in list_devices():
        device = InputDevice(path)
        if ecodes.EV_KEY in device.capabilities():
            if 'keyboard' in device.name.lower() or 'key' in device.name.lower() or 'at translated' in device.name.lower():
                devices.append(device)
                logger.info(f"Found keyboard device: {device.path} - {device.name}")
                print(f"  ✓ {device.path} - {device.name}")

    if not devices:
        raise RuntimeError("No keyboard devices found!")

    return devices


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='/var/log/transcription_listener.log',
    filemode='a'  # 'a' für Anhängen, 'w' für Überschreiben bei jedem Start
)


def audio_callback(indata, frames, time, status):
    """Callback to capture audio data"""
    global audio_data, recording
    if recording:
        audio_data.append(indata.copy())

def start_recording():
    global recording, audio_data, input_stream
    if not recording:
        device_name = sd.query_devices(device_index)['name']
        msg = f"🎤 Recording from DEVICE {device_index}: {device_name}"
        logger.info(msg)
        print(msg)

        recording = True
        audio_data = []

        try:
            input_stream = sd.InputStream(
                device=device_index,
                samplerate=samplerate,
                channels=1,
                dtype='int16',
                callback=audio_callback
            )
            input_stream.start()
            logger.info("InputStream started")
        except Exception as e:
            logger.error(f"Error starting input stream: {e}")
            recording = False

def stop_recording():
    global recording, audio_data, input_stream
    if recording:
        logger.info("Recording stopped...")
        print(">>> ⏹️ RECORDING STOPPED <<<\n")
        recording = False

        if input_stream:
            input_stream.stop()
            input_stream.close()
            input_stream = None

        if audio_data and len(audio_data) > 0:
            msg = f"✓ Recording completed: {sum(len(d) for d in audio_data)} samples"
            logger.info(msg)
            print(msg)
            save_audio()
            transcribe_and_output()
        else:
            logger.warning("No audio data recorded")
            print("⚠️  No audio data recorded")

def save_audio():
    global audio_data
    try:
        if not audio_data or len(audio_data) == 0:
            logger.warning("No audio data to save.")
            return

        # Concatenate all audio chunks
        audio_array = np.concatenate(audio_data, axis=0)
        sf.write(file_path, audio_array, samplerate=samplerate, subtype='PCM_16')
        logger.info(f"Audio saved to {file_path} ({len(audio_array)} samples)")
        print(f"✓ Audio saved to {file_path}")
    except Exception as e:
        logger.error(f"Error saving audio: {e}")
        print(f"✗ Error saving audio: {e}")


alt_press_times = []
keyboard_lock = threading.Lock()
DOUBLE_TAP_TIMEOUT = 0.5  # 500ms window for double-tap

def monitor_device(device):
    try:
        logger.info(f"Monitoring device: {device.path}")
        print(f"✓ Listening on: {device.path} ({device.name})\n")
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                key_event = evdev.categorize(event)
                keycode = key_event.keycode
                keystate = key_event.keystate

                # Only react to Alt PRESS events
                if keycode in ['KEY_LEFTALT', 'KEY_RIGHTALT'] and keystate == 1:
                    with keyboard_lock:
                        current_time = time.time()

                        # Remove old presses outside the window
                        alt_press_times[:] = [t for t in alt_press_times if current_time - t < DOUBLE_TAP_TIMEOUT]

                        alt_press_times.append(current_time)

                        logger.debug(f"Alt press #{len(alt_press_times)}")

                        # Check for double-tap (2 presses within timeout)
                        if len(alt_press_times) >= 2:
                            logger.info(f"*** DOUBLE-TAP DETECTED ({len(alt_press_times)} presses) ***")

                            if not recording:
                                print("\n>>> 🔴 RECORDING STARTED <<<")
                                print("🎤 Sprechen Sie jetzt! Drücken Sie Alt zweimal zum Stoppen.\n")
                                start_recording()
                            else:
                                print("\n>>> ⏹️  RECORDING STOPPED <<<\n")
                                stop_recording()

                            # Reset the press counter
                            alt_press_times.clear()

    except Exception as e:
        logger.error(f"Error monitoring {device.path}: {e}")

def process_keyboard_events(devices):
    threads = []
    for device in devices:
        t = threading.Thread(target=monitor_device, args=(device,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("Exiting...")
        global recording
        if recording:
            stop_recording()
        print("\n✓ Goodbye!")

def transcribe_with_whisper(audio_file_path):
    try:
        model = whisper.load_model("base")
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        result = model.transcribe(audio_file_path,  fp16=True, language="de", task="transcribe")

        transcription = result["text"]
        logging.info(f"Transcription result: {transcription}")

        return transcription

    except Exception as e:
        logging.error(f"Failed to transcribe audio with Whisper: {e}")
        raise

def type_text_in_active_window(text):
    """Copy text to clipboard using xclip"""
    print(f"\n📋 Copying {len(text)} characters to clipboard...")
    logger.info(f"Copying to clipboard: {text}")

    try:
        # Try xclip first
        result = subprocess.run(["which", "xclip"], capture_output=True)
        if result.returncode == 0:
            # Use xclip
            process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            print(f"✓ Text copied to clipboard (xclip)")
            print(f"\n🖱️  Now use Ctrl+V to paste!\n")
            logger.info("Text copied to clipboard using xclip")
            return

        # Fallback to xsel
        result = subprocess.run(["which", "xsel"], capture_output=True)
        if result.returncode == 0:
            process = subprocess.Popen(["xsel", "-bi"], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
            print(f"✓ Text copied to clipboard (xsel)")
            print(f"\n🖱️  Now use Ctrl+V to paste!\n")
            logger.info("Text copied to clipboard using xsel")
            return

        # No clipboard tool found
        print("❌ ERROR: xclip or xsel not found!")
        print(f"   Text: {text}")
        logger.error("No clipboard tool available")

    except Exception as e:
        print(f"❌ Error copying to clipboard: {e}")
        print(f"   Text: {text}")
        logger.error(f"Error copying to clipboard: {e}")


def transcribe_and_output():
    try:
        # Hinweis auf Start der Transkription
        print("Starting transcription...")
        logging.info("Starting transcription...")

        transcription = transcribe_with_whisper(file_path)

        if not transcription or transcription.strip() == "":
            print("No valid transcription found.")
            logging.info("No valid transcription generated.")
            return

        # Transkription ausgeben und ins aktive Fenster eingeben
        print(f"Transcription: {transcription}")
        logging.info(f"Transcription: {transcription}")
        type_text_in_active_window(transcription)
    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}")
        print(f"An error occurred during transcription: {e}")


if __name__ == "__main__":
    # Modellname bestimmen
    llm_model = os.environ.get('GEMINI_LLM', 'gemini-2.5-flash-lite-preview-06-17')
    print(f"Verwendetes LLM-Modell: {llm_model}")

    # Audio device selection
    try:
        select_audio_device()
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        exit(1)

    # Konfiguration beim Start ausgeben
    device_info = sd.query_devices(device_index)
    device_name = device_info['name']
    device_channels = device_info['max_input_channels']

    print("\n" + "="*60)
    print(f"🎤 AUDIO DEVICE: #{device_index} - {device_name}")
    print(f"   Channels: {device_channels}")
    print(f"   Sample Rate: {samplerate} Hz")
    print("="*60)

    print("\nKonfiguration beim Start:")
    print(f"samplerate: {samplerate}")
    print(f"file_path: {file_path}")
    print(f"Audio Device: {device_index} ({device_name})")
    print(f"LC_ALL: {os.environ.get('LC_ALL')}")
    print(f"LANG: {os.environ.get('LANG')}")

    try:
        print("\nDetecting keyboard devices...")
        keyboard_devices = find_keyboard_devices()
        print(f"\nFound {len(keyboard_devices)} keyboard device(s):")
        for dev in keyboard_devices:
            print(f"  → {dev.path} ({dev.name})")
        print("\nHold Ctrl + Alt to start recording. Release to stop recording and transcribe.")
        print("Press Ctrl+C to exit.\n")
        process_keyboard_events(keyboard_devices)
    except PermissionError:
        print("ERROR: Need permission to access /dev/input devices!")
        print("Try running with: sudo python transcription_offline.py")
        logger.error("PermissionError: Cannot access /dev/input devices")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        logger.error(f"RuntimeError: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"Unexpected error: {e}")