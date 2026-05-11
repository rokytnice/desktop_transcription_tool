#!/usr/bin/env python3

import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import subprocess
import sys
import signal
import time
import logging
import whisper
import torch
import evdev
from evdev import InputDevice, ecodes, list_devices
import threading
import argparse

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False

# Setup writable directory for logs and audio files
TRANSCRIPTION_DIR = os.path.expanduser("~/.transcription")
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

file_path = os.path.join(TRANSCRIPTION_DIR, "audio_recording.wav")
log_file_path = os.path.join(TRANSCRIPTION_DIR, "transcription_listener.log")

audio_data = []
input_stream = None

samplerate = 16000
device_index = None  # Input device, selected at startup
output_device_index = None  # Output device, selected at startup

# Auto-detect best audio device if AUDIO_DEVICE env var is set
def get_audio_device_from_env():
    """Get audio device from environment variable or return None"""
    env_device = os.environ.get('AUDIO_DEVICE')
    if env_device:
        try:
            return int(env_device)
        except ValueError:
            return None
    return None

# Logger erstellen
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Ausgabe in eine Datei
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Ausgabe in die Konsole
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

current_keys = set()

def _generate_beep_wav(filepath, frequency=1000, duration=0.2, volume=0.5):
    """Generate a beep WAV file"""
    sample_rate = 48000
    samples = int(sample_rate * duration)
    t = np.linspace(0, duration, samples)
    waveform = (np.sin(2 * np.pi * frequency * t) * volume * 32767).astype(np.int16)
    waveform_stereo = np.column_stack([waveform, waveform])
    sf.write(filepath, waveform_stereo, sample_rate, subtype='PCM_16')

# Pre-generate beep WAVs once
START_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "start_beep.wav")
STOP_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "stop_beep.wav")
_generate_beep_wav(START_BEEP_PATH, frequency=800, duration=0.15, volume=0.5)
_generate_beep_wav(STOP_BEEP_PATH, frequency=1200, duration=0.2, volume=0.5)

def play_beep(filepath):
    """Play a WAV file via sounddevice on selected output device (blocking)"""
    try:
        data, fs = sf.read(filepath, dtype='int16')
        sd.play(data, fs, device=output_device_index, blocking=True)
        sd.stop()
    except Exception as e:
        logger.warning(f"Could not play sound: {e}")

def play_start_recording_sound():
    """Play sound when recording starts"""
    play_beep(START_BEEP_PATH)

def play_stop_recording_sound():
    """Play sound when recording stops"""
    play_beep(STOP_BEEP_PATH)

# Audio output device selection
def select_output_device(interactive=False):
    """Show available audio output devices and let user select one, or use default"""
    global output_device_index

    # Check env var first
    env_device = os.environ.get('AUDIO_OUTPUT_DEVICE')
    if env_device:
        try:
            output_device_index = int(env_device)
            dev_info = sd.query_devices(output_device_index)
            print(f"✓ Using output from environment: {dev_info['name']}\n")
            return output_device_index
        except Exception as e:
            logger.warning(f"AUDIO_OUTPUT_DEVICE env var invalid: {e}")

    # If not interactive, use default device
    if not interactive:
        output_device_index = sd.default.device[1]
        dev_info = sd.query_devices(output_device_index)
        logger.info(f"Using default output device: {output_device_index} - {dev_info['name']}")
        return output_device_index

    print("\n=== AVAILABLE OUTPUT DEVICES (Lautsprecher/Kopfhörer) ===\n")

    devices_list = []
    all_devices = sd.query_devices()

    for idx, device in enumerate(all_devices):
        if device['max_output_channels'] > 0:
            devices_list.append(idx)
            is_default = " ← DEFAULT" if idx == sd.default.device[1] else ""
            print(f"[{len(devices_list)-1}] Device #{idx}: {device['name']}{is_default}")
            print(f"         Channels: {device['max_output_channels']}, Rate: {device['default_samplerate']} Hz")

    print()
    if len(devices_list) == 0:
        logger.warning("No audio output devices found!")
        output_device_index = None
        return None

    while True:
        try:
            choice = input(f"Select OUTPUT device for beeps [0-{len(devices_list)-1}]: ").strip()
            choice_idx = int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            output_device_index = devices_list[choice_idx]
            selected_name = all_devices[output_device_index]['name']
            print(f"\n✓ Output: {selected_name}\n")
            logger.info(f"Selected output device {output_device_index}: {selected_name}")
            return output_device_index
        except ValueError:
            print("Please enter a number!")

# Audio device selection
def select_audio_device(interactive=False):
    """Show available audio input devices and let user select one, or use default"""
    global device_index

    # Check for environment variable first (for systemd service)
    env_device = get_audio_device_from_env()
    if env_device is not None:
        try:
            dev_info = sd.query_devices(env_device)
            if dev_info['max_input_channels'] > 0:
                device_index = env_device
                logger.info(f"Using device from AUDIO_DEVICE env var: {env_device} - {dev_info['name']}")
                print(f"✓ Using device from environment: {dev_info['name']}\n")
                return device_index
        except Exception as e:
            logger.warning(f"AUDIO_DEVICE env var invalid: {e}")

    # If not interactive, use default device
    if not interactive:
        device_index = sd.default.device[0]
        dev_info = sd.query_devices(device_index)
        if dev_info['max_input_channels'] > 0:
            logger.info(f"Using default input device: {device_index} - {dev_info['name']}")
            return device_index

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


def audio_callback(indata, frames, time, status):
    """Callback to capture audio data"""
    global audio_data, recording
    if recording:
        audio_data.append(indata.copy())

def start_recording():
    global recording, audio_data, input_stream, samplerate
    if not recording:
        device_info = sd.query_devices(device_index)
        device_name = device_info['name']
        # Use device's native sample rate and channel count
        device_samplerate = int(device_info['default_samplerate'])
        device_channels = min(device_info['max_input_channels'], 2)
        samplerate = device_samplerate

        msg = f"🎤 Recording from DEVICE {device_index}: {device_name} @ {device_samplerate}Hz, {device_channels}ch"
        logger.info(msg)
        print(msg)

        # Set recording flag FIRST to prevent re-entry during beep
        recording = True
        audio_data = []

        # Play beep BEFORE opening stream to avoid audio system conflicts
        play_start_recording_sound()

        try:
            input_stream = sd.InputStream(
                device=device_index,
                samplerate=device_samplerate,
                channels=device_channels,
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

_shutdown_requested = False

def process_keyboard_events(devices):
    global _shutdown_requested
    threads = []
    for device in devices:
        t = threading.Thread(target=monitor_device, args=(device,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while not _shutdown_requested:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    # Clean shutdown
    logger.info("Exiting...")
    print("\n⏹️  Shutting down...")
    global recording
    if recording:
        try:
            stop_recording()
        except Exception:
            pass
    # Close all input devices
    for device in devices:
        try:
            device.close()
        except Exception:
            pass
    print("✓ Goodbye!")
    os._exit(0)  # Force exit (daemon threads in read_loop won't stop otherwise)

_whisper_model = None

def get_whisper_model():
    """Load and cache Whisper model on first call"""
    global _whisper_model
    if _whisper_model is None:
        model_name = os.environ.get('WHISPER_MODEL', 'small')
        print(f"📥 Loading Whisper {model_name} model (one-time)...")
        logger.info(f"Loading Whisper {model_name} model...")
        _whisper_model = whisper.load_model(model_name)
        logger.info(f"Whisper {model_name} model loaded")
        print(f"✓ Whisper {model_name} ready")
    return _whisper_model

def transcribe_with_whisper(audio_file_path):
    try:
        model = get_whisper_model()
        result = model.transcribe(audio_file_path, language="de", task="transcribe")

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
        play_stop_recording_sound()
    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}")
        print(f"An error occurred during transcription: {e}")


def _signal_handler(signum, frame):
    global _shutdown_requested
    print(f"\n⏹️  Received signal {signum}, shutting down...")
    _shutdown_requested = True

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Desktop Transcription Tool (Offline)")
    parser.add_argument('-H', '--interactive', action='store_true',
                        help='Show device selection menu (default: use default devices)')
    args = parser.parse_args()

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    # Modellname bestimmen
    # Pre-load Whisper model (saves time on first recording)
    try:
        get_whisper_model()
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        logger.error(f"Error loading Whisper model: {e}")

    # Audio device selection
    try:
        select_audio_device(interactive=args.interactive)
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        exit(1)

    # Output device selection (for beeps)
    try:
        select_output_device(interactive=args.interactive)
    except Exception as e:
        print(f"Error selecting output device: {e}")
        # Continue without output device (beeps will use default)

    # Set explicit default devices for sounddevice (prevents I/O combination errors)
    if device_index is not None and output_device_index is not None:
        sd.default.device = [device_index, output_device_index]
        logger.info(f"Default devices set: input={device_index}, output={output_device_index}")

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