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
import queue

os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False
_shutdown_requested = False

TRANSCRIPTION_DIR = os.path.expanduser("~/.transcription")
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

log_file_path = os.path.join(TRANSCRIPTION_DIR, "transcription_streaming.log")

samplerate = 16000
device_index = None
output_device_index = None

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

current_keys = set()
_whisper_model = None
audio_queue = queue.Queue()

def get_whisper_model():
    """Load Whisper model once and cache it"""
    global _whisper_model
    if _whisper_model is None:
        model_name = os.environ.get('WHISPER_MODEL', 'small')
        logger.info(f"Loading Whisper {model_name} model...")
        print(f"Loading Whisper {model_name} model...")
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model

def get_audio_device_from_env():
    """Get audio device from environment variable or return None"""
    env_device = os.environ.get('AUDIO_DEVICE')
    if env_device:
        try:
            return int(env_device)
        except ValueError:
            return None
    return None

def select_audio_device(interactive=False):
    """Select audio input device"""
    global device_index

    env_device = get_audio_device_from_env()
    if env_device is not None:
        try:
            dev_info = sd.query_devices(env_device)
            if dev_info['max_input_channels'] > 0:
                device_index = env_device
                logger.info(f"Using device from AUDIO_DEVICE env var: {env_device}")
                print(f"✓ Using device from environment: {dev_info['name']}\n")
                return device_index
        except Exception as e:
            logger.warning(f"AUDIO_DEVICE env var invalid: {e}")

    if not interactive:
        device_index = sd.default.device[0]
        dev_info = sd.query_devices(device_index)
        if dev_info['max_input_channels'] > 0:
            logger.info(f"Using default input device: {device_index}")
            return device_index

    print("\n=== AVAILABLE MICROPHONE DEVICES ===\n")
    devices_list = []
    all_devices = sd.query_devices()

    for idx, device in enumerate(all_devices):
        if device['max_input_channels'] > 0:
            devices_list.append(idx)
            is_default = " ← DEFAULT" if idx == sd.default.device[0] else ""
            print(f"[{len(devices_list)-1}] Device #{idx}: {device['name']}{is_default}")
            print(f"         Channels: {device['max_input_channels']}, Rate: {device['default_samplerate']} Hz")

    print()
    if len(devices_list) == 1:
        device_index = devices_list[0]
        return device_index

    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}]: ").strip()
            choice_idx = int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                continue
            device_index = devices_list[choice_idx]
            logger.info(f"Selected device {device_index}")
            return device_index
        except ValueError:
            pass

def type_text_in_active_window(text):
    """Type text in the active window using xdotool"""
    if not text or text.strip() == "":
        return

    try:
        cmd = ['xdotool', 'type', '--delay', '10', '--', text]
        subprocess.run(cmd, check=True)
        logger.info(f"Typed text: {text}")
    except Exception as e:
        logger.error(f"Error typing text: {e}")

def select_output_device(interactive=False):
    """Select audio output device for beeps"""
    global output_device_index

    env_device = os.environ.get('AUDIO_OUTPUT_DEVICE')
    if env_device:
        try:
            output_device_index = int(env_device)
            dev_info = sd.query_devices(output_device_index)
            logger.info(f"Using output from environment: {output_device_index}")
            return output_device_index
        except Exception as e:
            logger.warning(f"AUDIO_OUTPUT_DEVICE env var invalid: {e}")

    if not interactive:
        output_device_index = sd.default.device[1]
        logger.info(f"Using default output device: {output_device_index}")
        return output_device_index

    print("\n=== AVAILABLE OUTPUT DEVICES ===\n")
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
        return None

    while True:
        try:
            choice = input(f"Select OUTPUT device [0-{len(devices_list)-1}]: ").strip()
            choice_idx = int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                continue
            output_device_index = devices_list[choice_idx]
            logger.info(f"Selected output device {output_device_index}")
            return output_device_index
        except ValueError:
            pass

def find_keyboard_devices():
    """Find keyboard input devices"""
    devices = []
    for device_path in list_devices():
        try:
            device = InputDevice(device_path)
            caps = device.capabilities()
            if ecodes.EV_KEY in caps:
                for key in caps[ecodes.EV_KEY]:
                    if isinstance(key, tuple):
                        key_code = key[0]
                    else:
                        key_code = key
                    if key_code == ecodes.KEY_A:
                        devices.append(device)
                        logger.info(f"Found keyboard device: {device_path} ({device.name})")
                        break
        except:
            pass
    return devices

def transcribe_audio_chunk(audio_data, samplerate):
    """Transcribe a chunk of audio and return the text"""
    if len(audio_data) == 0:
        return ""

    try:
        model = get_whisper_model()
        result = model.transcribe(
            audio_data,
            language="de",
            fp16=torch.cuda.is_available(),
            verbose=False
        )
        text = result["text"].strip()
        return text
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""

class StreamingTranscriber:
    """Real-time streaming transcription"""
    def __init__(self):
        self.audio_buffer = np.array([], dtype=np.float32)
        self.chunk_duration = 2  # seconds
        self.chunk_samples = int(samplerate * self.chunk_duration)
        self.is_recording = False
        self.last_transcribed = ""

    def audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback"""
        if status:
            logger.warning(f"Audio status: {status}")
        self.audio_buffer = np.append(self.audio_buffer, indata[:, 0])

    def process_stream(self):
        """Process audio in chunks and transcribe"""
        while self.is_recording and not _shutdown_requested:
            if len(self.audio_buffer) >= self.chunk_samples:
                chunk = self.audio_buffer[:self.chunk_samples]
                self.audio_buffer = self.audio_buffer[self.chunk_samples:]

                text = transcribe_audio_chunk(chunk, samplerate)
                if text and text != self.last_transcribed:
                    logger.info(f"Stream output: {text}")
                    type_text_in_active_window(text + " ")
                    self.last_transcribed = text

            time.sleep(0.1)

    def start_streaming(self):
        """Start streaming transcription"""
        global recording

        self.is_recording = True
        recording = True

        logger.info("🎤 Starting streaming transcription...")
        print("🎤 Streaming transcription started. Speak now...")

        try:
            with sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=samplerate,
                callback=self.audio_callback,
                blocksize=4096
            ):
                process_thread = threading.Thread(target=self.process_stream)
                process_thread.daemon = True
                process_thread.start()

                while self.is_recording and not _shutdown_requested:
                    time.sleep(0.1)

        except Exception as e:
            logger.error(f"Stream error: {e}")
            print(f"Error: {e}")
        finally:
            self.is_recording = False
            recording = False
            logger.info("Streaming transcription stopped")

def monitor_keyboard_device(device):
    """Monitor single keyboard device for Alt+Alt"""
    global _shutdown_requested

    alt_press_times = []
    DOUBLE_TAP_TIMEOUT = 0.5
    streaming = None

    try:
        logger.info(f"Listening on: {device.path} ({device.name})")
        for event in device.read_loop():
            if _shutdown_requested:
                break

            if event.type == ecodes.EV_KEY:
                key_event = evdev.categorize(event)
                keycode = key_event.keycode
                keystate = key_event.keystate

                if keycode in ['KEY_LEFTALT', 'KEY_RIGHTALT'] and keystate == 1:
                    current_time = time.time()
                    alt_press_times[:] = [t for t in alt_press_times if current_time - t < DOUBLE_TAP_TIMEOUT]
                    alt_press_times.append(current_time)

                    logger.debug(f"Alt press #{len(alt_press_times)}")

                    if len(alt_press_times) >= 2:
                        logger.info(f"Alt+Alt detected - toggling streaming")

                        if streaming is None or not streaming.is_recording:
                            streaming = StreamingTranscriber()
                            streaming.start_streaming()
                        else:
                            streaming.is_recording = False

                        alt_press_times.clear()

    except Exception as e:
        logger.error(f"Error monitoring {device.path}: {e}")
    finally:
        if streaming and streaming.is_recording:
            streaming.is_recording = False

def listen_for_double_alt(keyboard_devices):
    """Listen for Alt+Alt on all keyboard devices using threads"""
    threads = []
    for device in keyboard_devices:
        t = threading.Thread(target=monitor_keyboard_device, args=(device,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while not _shutdown_requested:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    logger.info("Exiting...")
    print("\n⏹️  Shutting down...")

    for device in keyboard_devices:
        try:
            device.close()
        except:
            pass

    os._exit(0)

def _signal_handler(signum, frame):
    global _shutdown_requested
    print(f"\n⏹️  Shutting down...")
    _shutdown_requested = True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time Streaming Transcription")
    parser.add_argument('-H', '--interactive', action='store_true',
                        help='Show device selection menu')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        get_whisper_model()
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        logger.error(f"Error loading Whisper model: {e}")
        sys.exit(1)

    try:
        select_audio_device(interactive=args.interactive)
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        sys.exit(1)

    try:
        select_output_device(interactive=args.interactive)
    except Exception as e:
        logger.warning(f"Error selecting output device: {e}")

    device_info = sd.query_devices(device_index)
    print(f"\n{'='*60}")
    print(f"🎤 AUDIO DEVICE: #{device_index} - {device_info['name']}")
    print(f"   Sample Rate: {samplerate} Hz")
    print(f"   Mode: Real-time Streaming Transcription")
    print(f"{'='*60}\n")

    try:
        logger.info("Starting streaming transcription listener...")
        keyboard_devices = find_keyboard_devices()
        print(f"Found {len(keyboard_devices)} keyboard device(s)")
        if keyboard_devices:
            listen_for_double_alt(keyboard_devices)
        else:
            print("ERROR: No keyboard devices found!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"ERROR: {e}")
        sys.exit(1)

    os._exit(0)
