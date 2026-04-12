#!/usr/bin/env python3
"""
Transcription Daemon v3 - Phase 3
With Silero VAD (auto-stop on silence) - VAD optional/lazy-loaded
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.12', 'site-packages'))

import socket
import json
import time
import logging
import signal
from pathlib import Path
from threading import Thread, Event
import numpy as np

import sounddevice as sd
import subprocess

import whisper  # Official OpenAI Whisper

from evdev import InputDevice, ecodes, list_devices
import select

# Logging
log_dir = Path.home() / ".local" / "share" / "transcribe"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "daemon_v3.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Config
SOCKET_FILE = Path.home() / ".cache" / "transcribe.sock"
SAMPLE_RATE = 16000
CHANNELS = 1
MODEL_NAME = "base"  # Better accuracy, fewer hallucinations (slight speed trade-off)
DOUBLE_TAP_TIMEOUT = 0.5
MIN_RECORDING_TIME = 1.0
SILENCE_THRESHOLD = 0.5  # seconds of silence before auto-stop
VAD_THRESHOLD = 0.5  # confidence threshold for speech

# Global state
recording = False
audio_data = []
input_stream = None
recording_start_time = None
alt_press_times = []
model = None
vad_model = None
HAS_VAD = False
stop_event = Event()
silence_start = None
streaming = False
previous_injected = ""
stream_thread = None
last_injected_text = ""  # Track to avoid duplicates
STREAM_INTERVAL = 5.0  # Re-transcribe every 5 seconds (larger buffer = more context, fewer false positives)

def load_models():
    """Load Whisper and VAD models on startup"""
    global model, vad_model, HAS_VAD

    logger.info(f"Loading Whisper model ({MODEL_NAME}) - Official OpenAI...")
    try:
        model = whisper.load_model(MODEL_NAME, device="cpu")
        logger.info("✓ Whisper model loaded")
    except Exception as e:
        logger.error(f"Failed to load Whisper: {e}")
        return False

    # Try to load VAD (lazy import to avoid CUDA errors)
    logger.info("Loading Silero VAD...")
    try:
        import torch
        from silero_vad import load_silero_vad
        vad_model = load_silero_vad()
        HAS_VAD = True
        logger.info("✓ VAD model loaded (auto-stop on 0.5s silence)")
    except Exception as e:
        logger.warning(f"VAD not available: {e} (manual stop only)")
        HAS_VAD = False

    return True

def remove_duplicate_phrases(text):
    """Remove repeated phrases from Whisper hallucinations"""
    sentences = text.split(". ")
    unique = []
    for sent in sentences:
        sent = sent.strip()
        if sent and sent not in unique:
            unique.append(sent)
    return ". ".join(unique) + ("." if text.endswith(".") else "")

def filter_hallucinations(text):
    """Remove obvious Whisper hallucinations (minimal filtering - base model reduces most)"""
    import re

    # Only filter the most egregious hallucinations
    # The 'base' model is much better trained, so we don't need extensive patterns
    patterns = [
        r'(?i)copyright\s+\w+\s+\d{4}',  # Copyright notices
        r'(?i)©\s*\d{4}',                  # © symbol with year
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text).strip()

    # Remove standalone dots/ellipsis/punctuation
    if not re.search(r'[a-zA-Z0-9äöüßÄÖÜ]', text):
        # No alphanumeric characters (only punctuation/spaces)
        return ''

    # Clean up excessive trailing dots
    text = re.sub(r'\.{2,}$', '.', text)

    return text.strip()

def is_silence(audio, threshold=0.01):
    """Detect if audio is mostly silence (RMS too low)"""
    rms = np.sqrt(np.mean(audio ** 2))
    return rms < threshold

def find_new_text(previous, current):
    """Extract only new words from transcription"""
    import difflib

    # Remove duplicates first
    current = remove_duplicate_phrases(current)

    if not previous:
        return current

    # If current starts with previous (exact), return the new part
    if current.startswith(previous):
        new = current[len(previous):]
        return new.lstrip()

    # Normalize for comparison: lowercase, remove punctuation
    prev_norm = previous.lower().replace(".", "").replace(",", "").strip()
    curr_norm = current.lower().replace(".", "").replace(",", "").strip()

    # If normalized versions match, no new text
    if prev_norm == curr_norm:
        return ""

    # Find longest common substring at the start (character level)
    match_len = 0
    for i in range(min(len(previous), len(current))):
        if previous[i] == current[i]:
            match_len = i + 1
        else:
            break

    # Return text after the matching portion
    if match_len < len(current):
        return current[match_len:].lstrip()

    return ""

def play_beep(frequency=1000, duration=0.2):
    """Play a beep tone"""
    try:
        beep_audio = np.sin(2 * np.pi * np.arange(int(SAMPLE_RATE * duration)) * frequency / SAMPLE_RATE).astype(np.float32) * 0.3
        sd.play(beep_audio, SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        logger.debug(f"Beep failed: {e}")

def streaming_transcriber():
    """Background thread: transcribe audio every 5 seconds while recording"""
    global recording, audio_data, previous_injected, model, last_injected_text

    while recording:
        time.sleep(STREAM_INTERVAL)

        if not recording or len(audio_data) == 0:
            continue

        try:
            # Transcribe all audio accumulated so far
            audio = np.concatenate(audio_data, axis=0).flatten()
            duration = len(audio) / SAMPLE_RATE

            if duration < 2.0:  # Wait for at least 2 seconds of audio
                continue

            # Skip if audio is mostly silence (no speech)
            if is_silence(audio):
                continue

            # Official Whisper API: pass numpy array directly (streaming, no temp files)
            result = model.transcribe(audio, language="de", task="transcribe")
            current_text = result["text"].strip()

            # Filter out hallucinations (copyright notices, metadata, etc.)
            current_text = filter_hallucinations(current_text)

            # Skip if empty (no logging)
            if not current_text:
                continue

            # Find new words
            new_text = find_new_text(previous_injected, current_text)

            # Only inject if new text AND different from last injection (avoid duplicates)
            if new_text and new_text != last_injected_text:
                logger.info(f"🔴 STREAMING: '{new_text}'")
                inject_text(new_text)
                previous_injected = current_text
                last_injected_text = new_text

        except Exception as e:
            logger.debug(f"Streaming error: {e}")

def start_recording():
    global recording, audio_data, input_stream, recording_start_time, silence_start, streaming, stream_thread, previous_injected, last_injected_text
    if not recording:
        mode = " (real-time streaming)"
        logger.info(f"Recording started{mode}")
        print(f"🎤 RECORDING{mode}")
        play_beep(frequency=800, duration=0.15)
        recording = True
        streaming = True
        previous_injected = ""
        last_injected_text = ""
        recording_start_time = time.time()
        silence_start = None
        audio_data = []
        input_stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                     dtype='float32', callback=audio_callback_vad)
        input_stream.start()

        stream_thread = Thread(target=streaming_transcriber, daemon=True)
        stream_thread.start()

def audio_callback_vad(indata, frames, time_info, status):
    """Audio callback with VAD detection"""
    global recording, silence_start, audio_data, vad_model, HAS_VAD

    if recording:
        audio_data.append(indata.copy())

        # VAD detection (if available)
        if HAS_VAD and vad_model:
            try:
                import torch
                audio_chunk = torch.from_numpy(indata.flatten())
                confidence = vad_model(audio_chunk, SAMPLE_RATE).item()

                if confidence < VAD_THRESHOLD:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > SILENCE_THRESHOLD:
                        logger.info("Silence detected, auto-stopping...")
                        recording = False
                else:
                    silence_start = None
            except Exception as e:
                logger.debug(f"VAD error: {e}")

def stop_recording():
    global recording, input_stream, audio_data, streaming, stream_thread, previous_injected, model
    if recording:
        elapsed = time.time() - recording_start_time
        if elapsed < MIN_RECORDING_TIME:
            time.sleep(MIN_RECORDING_TIME - elapsed)

        recording = False
        streaming = False

        if input_stream:
            input_stream.stop()
            input_stream.close()

        # Wait for streaming thread to finish
        if stream_thread:
            stream_thread.join(timeout=5)

        time.sleep(0.1)
        logger.info("Recording stopped")
        play_beep(frequency=400, duration=0.2)  # Lower beep for stop

        # Final transcription to get any remaining words
        if audio_data:
            try:
                audio = np.concatenate(audio_data, axis=0).flatten()
                duration = len(audio) / SAMPLE_RATE
                logger.info(f"📊 Final transcription of {duration:.1f}s audio...")

                # Official Whisper API: pass numpy array directly (streaming)
                result = model.transcribe(audio, language="de", task="transcribe")
                final_text = result["text"].strip()

                # Filter out hallucinations
                final_text = filter_hallucinations(final_text)

                # Inject any remaining new words
                new_text = find_new_text(previous_injected, final_text)
                if new_text:
                    logger.info(f"✅ FINAL TEXT: '{new_text}'")
                    inject_text(new_text)
                    previous_injected = final_text
                elif previous_injected:
                    logger.info(f"✅ TRANSCRIPTION COMPLETE: '{previous_injected}'")
                else:
                    logger.warning("⚠️  Empty transcription (no speech detected)")

            except Exception as e:
                logger.error(f"Final transcription error: {e}")

def transcribe_and_output():
    global audio_data, model

    if not audio_data:
        logger.warning("No audio recorded")
        return

    try:
        audio = np.concatenate(audio_data, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE
        logger.info(f"📊 Processing {len(audio)} samples ({duration:.1f}s audio)...")
        logger.info(f"🔄 Sending to Whisper model for transcription...")

        # Official Whisper API: pass numpy array directly (streaming)
        result = model.transcribe(audio, language="de", task="transcribe")
        text = result["text"].strip()

        if text:
            logger.info(f"✅ TRANSCRIPTION RESULT: '{text}'")
            logger.info(f"📝 Injecting {len(text)} chars into active window...")
            inject_text(text)
        else:
            logger.warning("⚠️  Empty transcription (no speech detected)")

    except Exception as e:
        logger.error(f"❌ Transcription error: {e}")

def inject_text(text):
    """Inject text via ydotool (Wayland-compatible)"""
    try:
        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = "/run/ydotool/.ydotool_socket"
        logger.info(f"🚀 Calling ydotool to inject text into active window...")
        subprocess.run(["ydotool", "type", text],
                      check=True, timeout=10, env=env)
        logger.info(f"✨ SUCCESS! Text injected into window: '{text}'")
    except subprocess.TimeoutExpired:
        logger.error(f"❌ ydotool timeout - text injection took too long")
    except FileNotFoundError:
        logger.error(f"❌ ydotool not found - make sure it's built and in PATH")
    except Exception as e:
        logger.error(f"❌ Text injection failed: {e}")

def get_keyboards():
    """Find keyboard devices"""
    keyboards = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            if ecodes.KEY_LEFTALT in device.capabilities().get(ecodes.EV_KEY, []):
                keyboards.append(device)
        except:
            pass
    return keyboards

def keyboard_listener():
    """Listen for Alt double-taps"""
    global alt_press_times, recording

    logger.info("Keyboard listener thread started")

    while not stop_event.is_set():
        try:
            keyboards = get_keyboards()
            if not keyboards:
                time.sleep(2)
                continue

            r, w, x = select.select(keyboards, [], [], 1)

            for device in r:
                try:
                    for event in device.read():
                        if event.type == ecodes.EV_KEY:
                            key = event.code
                            state = event.value

                            if key in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT) and state == 1:
                                key_name = "LEFT ALT" if key == ecodes.KEY_LEFTALT else "RIGHT ALT"
                                logger.info(f"🔑 Alt key pressed: {key_name}")
                                now = time.time()
                                alt_press_times[:] = [t for t in alt_press_times
                                                     if now - t < DOUBLE_TAP_TIMEOUT]

                                if len(alt_press_times) > 0:
                                    logger.info(f"🔄 DOUBLE-TAP DETECTED! {len(alt_press_times) + 1} presses")
                                    if recording:
                                        logger.info("⏹️  Stopping recording (double-tap detected)")
                                        stop_recording()
                                    else:
                                        logger.info("▶️  Starting recording (double-tap detected)")
                                        start_recording()
                                    alt_press_times.clear()
                                else:
                                    logger.info(f"⏳ First Alt press registered (waiting for second)")
                                    alt_press_times.append(now)
                except OSError:
                    break
        except Exception as e:
            logger.error(f"Keyboard listener error: {e}")
            time.sleep(1)

    logger.info("Keyboard listener thread stopped")

def handle_socket_client(sock_client, addr):
    """Handle incoming socket connection"""
    try:
        data = sock_client.recv(1024).decode('utf-8').strip()
        if not data:
            return

        logger.info(f"Socket command: {data}")
        response = {"status": "ok"}

        if data == "start":
            start_recording()
            msg = "VAD enabled" if HAS_VAD else "manual stop"
            response["message"] = f"Recording started ({msg})"
        elif data == "stop":
            stop_recording()
            response["message"] = "Recording stopped"
        elif data == "status":
            response["recording"] = recording
            response["vad_enabled"] = HAS_VAD
            response["message"] = ("🎤 RECORDING" if recording else "⏸️  IDLE")
        else:
            response["status"] = "error"
            response["message"] = f"Unknown command: {data}"

        sock_client.sendall(json.dumps(response).encode('utf-8'))
    except Exception as e:
        logger.error(f"Socket error: {e}")
    finally:
        sock_client.close()

def socket_server():
    """Listen on Unix socket"""
    global stop_event

    if SOCKET_FILE.exists():
        SOCKET_FILE.unlink()

    SOCKET_FILE.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(str(SOCKET_FILE))
    sock.listen(1)
    logger.info(f"Socket server listening on {SOCKET_FILE}")

    while not stop_event.is_set():
        try:
            sock.settimeout(1)
            try:
                client, _ = sock.accept()
                Thread(target=handle_socket_client, args=(client, None), daemon=True).start()
            except socket.timeout:
                pass
        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"Socket server error: {e}")

    sock.close()
    logger.info("Socket server stopped")

def main():
    logger.info("=" * 60)
    logger.info("Transcription Daemon v3 - Phase 3")
    logger.info("With Silero VAD (optional) + Auto-Stop on Silence")
    logger.info("=" * 60)

    if not load_models():
        logger.error("Failed to load models, exiting")
        return False

    kb_thread = Thread(target=keyboard_listener, daemon=True)
    kb_thread.start()
    logger.info("Keyboard listener started")

    sock_thread = Thread(target=socket_server, daemon=True)
    sock_thread.start()
    logger.info("Socket server started")

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("✓ Daemon v3 ready")
    if HAS_VAD:
        logger.info("✓ VAD enabled - auto-stops on 0.5s silence")
    else:
        logger.info("⚠ VAD disabled - use double-tap Alt to stop")
    logger.info("Ready for hotkey input or socket commands")

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        stop_event.set()

    logger.info("Daemon v3 stopped")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
