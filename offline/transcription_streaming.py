#!/usr/bin/env python3
#
# transcription_streaming.py — Echtzeit-Streaming-Transkription
#
# Im Gegensatz zur normalen Version (aufnehmen → stoppen → transkribieren)
# transkribiert diese Version KONTINUIERLICH während des Sprechens und tippt
# den Text direkt an der aktuellen Cursor-Position (via wtype, Wayland).
#
# Statt fixer Zeit-Chunks (die Wörter mittendrin zerschneiden) wird per
# einfacher Sprachaktivitäts-Erkennung (VAD) an natürlichen Sprechpausen
# segmentiert: sobald eine kurze Pause erkannt wird, wird die gesprochene
# Phrase transkribiert und sofort ausgegeben — ohne auf das Ende der gesamten
# Eingabe zu warten.

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
import queue
import argparse

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

# Setup writable directory for logs
TRANSCRIPTION_DIR = os.path.expanduser("~/.transcription")
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

log_file_path = os.path.join(TRANSCRIPTION_DIR, "transcription_streaming.log")

# Streaming uses a fixed 16 kHz mono float32 stream — Whisper's native format.
# PipeWire/PulseAudio resamples the device input transparently.
samplerate = 16000
BLOCKSIZE = 1600  # 0.1 s blocks → good resolution for pause detection

device_index = None       # Input device, selected at startup
output_device_index = None  # Output device (for beeps), selected at startup

# --- VAD / segmentation tuning (overridable via env) ---
SILENCE_RMS = float(os.environ.get('STREAM_SILENCE_RMS', '0.010'))   # below = silence
MIN_SILENCE = float(os.environ.get('STREAM_MIN_SILENCE', '0.7'))     # s pause to end phrase
MIN_PHRASE = float(os.environ.get('STREAM_MIN_PHRASE', '0.4'))       # s min phrase to transcribe
MAX_PHRASE = float(os.environ.get('STREAM_MAX_PHRASE', '15.0'))      # s force-flush long phrase

# Logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

_shutdown_requested = False
_whisper_model = None


def get_audio_device_from_env():
    """Get audio input device from environment variable or return None"""
    env_device = os.environ.get('AUDIO_DEVICE')
    if env_device:
        try:
            return int(env_device)
        except ValueError:
            return None
    return None


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


# ─────────────────────────── Beeps ───────────────────────────

def _generate_beep_wav(filepath, frequency=1000, duration=0.2, volume=0.5):
    sample_rate = 48000
    samples = int(sample_rate * duration)
    t = np.linspace(0, duration, samples)
    waveform = (np.sin(2 * np.pi * frequency * t) * volume * 32767).astype(np.int16)
    waveform_stereo = np.column_stack([waveform, waveform])
    sf.write(filepath, waveform_stereo, sample_rate, subtype='PCM_16')


START_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "start_beep.wav")
STOP_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "stop_beep.wav")
_generate_beep_wav(START_BEEP_PATH, frequency=800, duration=0.15, volume=0.5)
_generate_beep_wav(STOP_BEEP_PATH, frequency=1200, duration=0.2, volume=0.5)


def play_beep(filepath):
    try:
        subprocess.run(['paplay', filepath], timeout=2, check=True)
    except FileNotFoundError:
        try:
            data, fs = sf.read(filepath, dtype='int16')
            sd.play(data, fs, device=output_device_index, blocking=True)
            sd.stop()
        except Exception as e:
            logger.warning(f"Could not play sound: {e}")
    except Exception as e:
        logger.warning(f"Could not play sound via paplay: {e}")


# ─────────────────────── Type at cursor (Wayland) ───────────────────────
#
# Tipp-Mechanismus je nach Compositor:
#   • ydotool  — über /dev/uinput (Kernel-Ebene), funktioniert auf GNOME/KDE
#                Wayland. Bevorzugt. Braucht laufenden ydotoold-Daemon.
#   • wtype    — virtual-keyboard-Protokoll, nur wlroots (Sway/Hyprland).
#   • wl-copy  — Fallback: nur Zwischenablage, manuelles Ctrl+V nötig.
#
# TYPER wird beim Start ermittelt (detect_typer()).

YDOTOOL_SOCKET = os.environ.get('YDOTOOL_SOCKET') or f"/run/user/{os.getuid()}/.ydotool_socket"
TYPER = None  # 'ydotool' | 'wtype' | 'clipboard'


def _ydotool_env():
    env = dict(os.environ)
    env['YDOTOOL_SOCKET'] = YDOTOOL_SOCKET
    return env


def _ydotool_works():
    try:
        r = subprocess.run(['ydotool', 'type', '--file', '-'], input=b'',
                           env=_ydotool_env(), timeout=4, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def ensure_ydotoold():
    """Make sure a usable (user-owned) ydotoold is reachable; start one if not."""
    if _ydotool_works():
        return True
    try:
        subprocess.Popen(
            ['ydotoold', f'--socket-path={YDOTOOL_SOCKET}',
             f'--socket-own={os.getuid()}:{os.getgid()}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(15):
            time.sleep(0.3)
            if _ydotool_works():
                logger.info(f"Started user ydotoold (socket {YDOTOOL_SOCKET})")
                return True
    except FileNotFoundError:
        logger.warning("ydotoold not found")
    return _ydotool_works()


def _wtype_works():
    try:
        r = subprocess.run(['wtype', ''], timeout=4, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def detect_typer():
    """Pick the best available 'type at cursor' backend for this session."""
    global TYPER
    if ensure_ydotoold():
        TYPER = 'ydotool'
    elif _wtype_works():
        TYPER = 'wtype'
    else:
        TYPER = 'clipboard'
    logger.info(f"Typing backend: {TYPER}")
    return TYPER


def type_at_cursor(text):
    """Type text at the current cursor position using the detected backend."""
    if not text or not text.strip():
        return
    if TYPER == 'ydotool':
        try:
            # --file - reads from stdin with escaping disabled → literal text,
            # robust for umlauts/special chars and leading '-'.
            subprocess.run(['ydotool', 'type', '-d', '2', '--file', '-'],
                           input=text.encode('utf-8'), env=_ydotool_env(),
                           check=True, timeout=30)
            return
        except Exception as e:
            logger.error(f"ydotool error: {e}")
    elif TYPER == 'wtype':
        try:
            subprocess.run(['wtype', text], check=True, timeout=30)
            return
        except Exception as e:
            logger.error(f"wtype error: {e}")
    # Fallback: clipboard (manual paste)
    try:
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(text.encode('utf-8'))
        print(f"   📋 (kein Live-Tippen) in Zwischenablage: {text}")
        logger.warning("Used clipboard fallback (Ctrl+V to paste)")
    except Exception as e:
        logger.error(f"Clipboard fallback failed: {e}")
        print(f"   Text: {text}")


# ─────────────────────── Device selection ───────────────────────

def select_output_device(interactive=False):
    """Select audio output device for beeps, or use default."""
    global output_device_index

    env_device = os.environ.get('AUDIO_OUTPUT_DEVICE')
    if env_device:
        try:
            output_device_index = int(env_device)
            dev_info = sd.query_devices(output_device_index)
            print(f"✓ Using output from environment: {dev_info['name']}\n")
            return output_device_index
        except Exception as e:
            logger.warning(f"AUDIO_OUTPUT_DEVICE env var invalid: {e}")

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

    print()
    if len(devices_list) == 0:
        logger.warning("No audio output devices found!")
        output_device_index = None
        return None

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[1]), 0)
    while True:
        try:
            choice = input(f"Select OUTPUT device for beeps [0-{len(devices_list)-1}], Enter=Default: ").strip()
            choice_idx = default_list_idx if choice == "" else int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            output_device_index = devices_list[choice_idx]
            print(f"\n✓ Output: {all_devices[output_device_index]['name']}\n")
            return output_device_index
        except ValueError:
            print("Invalid selection!")


def select_auto_device():
    """Select ONE device for both input and output."""
    global device_index, output_device_index

    devices_list = []
    all_devices = sd.query_devices()
    for idx, device in enumerate(all_devices):
        if device['max_input_channels'] > 0 and device['max_output_channels'] > 0:
            devices_list.append(idx)

    if len(devices_list) == 0:
        raise RuntimeError("No devices with both input and output found!")

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[0]), 0)

    # Non-interactive mode (e.g. systemd service): use default automatically
    if not sys.stdin.isatty():
        choice_idx = default_list_idx
        device_index = devices_list[choice_idx]
        output_device_index = devices_list[choice_idx]
        selected_name = all_devices[device_index]['name']
        print(f"✓ Auto-selected default device: {selected_name} (Input + Output)\n")
        logger.info(f"Auto-selected device {device_index} for input and output: {selected_name}")
        return device_index

    print("\n=== SELECT DEVICE FOR INPUT + OUTPUT ===\n")
    for i, idx in enumerate(devices_list):
        device = all_devices[idx]
        is_default = " ← DEFAULT" if idx == sd.default.device[0] else ""
        print(f"[{i}] Device #{idx}: {device['name']}{is_default}")
    print()

    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}], Enter=Default: ").strip()
            choice_idx = default_list_idx if choice == "" else int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            device_index = devices_list[choice_idx]
            output_device_index = devices_list[choice_idx]
            selected_name = all_devices[device_index]['name']
            print(f"\n✓ Using: {selected_name} (Input + Output)\n")
            return device_index
        except ValueError:
            print("Invalid selection!")


def select_audio_device(interactive=False):
    """Select audio input device, or use default."""
    global device_index

    env_device = get_audio_device_from_env()
    if env_device is not None:
        try:
            dev_info = sd.query_devices(env_device)
            if dev_info['max_input_channels'] > 0:
                device_index = env_device
                print(f"✓ Using device from environment: {dev_info['name']}\n")
                return device_index
        except Exception as e:
            logger.warning(f"AUDIO_DEVICE env var invalid: {e}")

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

    print()
    if len(devices_list) == 0:
        raise RuntimeError("No audio input devices found!")
    if len(devices_list) == 1:
        device_index = devices_list[0]
        return device_index

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[0]), 0)
    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}], Enter=Default: ").strip()
            choice_idx = default_list_idx if choice == "" else int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            device_index = devices_list[choice_idx]
            print(f"\n✓ Using: {all_devices[device_index]['name']}\n")
            return device_index
        except ValueError:
            print("Invalid selection!")


# ─────────────────────── Streaming transcriber ───────────────────────

def transcribe_chunk(audio_float32):
    """Transcribe a float32 mono 16 kHz numpy array and return the text."""
    if audio_float32 is None or len(audio_float32) == 0:
        return ""
    try:
        model = get_whisper_model()
        result = model.transcribe(
            audio_float32,
            language="de",
            task="transcribe",
            fp16=torch.cuda.is_available(),
            verbose=False,
        )
        return result["text"].strip()
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


class StreamingTranscriber:
    """Continuously records, segments at speech pauses, transcribes and types
    each phrase at the cursor as soon as it is recognized."""

    def __init__(self):
        self.q = queue.Queue()       # (block_float32, rms) tuples from the audio callback
        self.active = False
        self.stream = None
        self.worker = None
        self.block_dur = BLOCKSIZE / samplerate

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        # indata is float32 [-1, 1]; take channel 0
        block = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0
        self.q.put((block, rms))

    def _flush(self, seg, seg_samples):
        """Transcribe an accumulated phrase and type it at the cursor."""
        if seg_samples < MIN_PHRASE * samplerate:
            return
        audio = np.concatenate(seg).astype(np.float32)
        text = transcribe_chunk(audio)
        if text:
            logger.info(f"Phrase ({seg_samples/samplerate:.1f}s) → {text!r}")
            print(f"📝 {text}")
            type_at_cursor(text + " ")

    def _worker(self):
        """Consume audio blocks, segment at pauses, flush phrases."""
        seg = []
        seg_samples = 0
        silence_run = 0.0
        in_speech = False

        while self.active or not self.q.empty():
            try:
                block, rms = self.q.get(timeout=0.1)
            except queue.Empty:
                continue

            voiced = rms >= SILENCE_RMS

            if voiced:
                in_speech = True
                seg.append(block)
                seg_samples += len(block)
                silence_run = 0.0
            elif in_speech:
                # trailing silence — keep it in the buffer, count the pause
                seg.append(block)
                seg_samples += len(block)
                silence_run += self.block_dur
                if silence_run >= MIN_SILENCE:
                    self._flush(seg, seg_samples)
                    seg, seg_samples, silence_run, in_speech = [], 0, 0.0, False
            # else: leading silence before any speech → drop

            # force-flush very long phrases (no pause yet)
            if seg_samples >= MAX_PHRASE * samplerate:
                self._flush(seg, seg_samples)
                seg, seg_samples, silence_run, in_speech = [], 0, 0.0, False

        # final flush when streaming stops
        if seg_samples > 0:
            self._flush(seg, seg_samples)

    def start(self):
        if self.active:
            return
        self.active = True
        # drain any stale blocks
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

        play_beep(START_BEEP_PATH)
        print("\n>>> 🔴 STREAMING GESTARTET <<<")
        print("🎤 Sprechen Sie — Text erscheint live am Cursor. Alt+Alt zum Stoppen.\n")
        logger.info("Streaming started")

        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

        self.stream = sd.InputStream(
            device=device_index,
            channels=1,
            samplerate=samplerate,
            dtype='float32',
            blocksize=BLOCKSIZE,
            callback=self._audio_callback,
        )
        self.stream.start()

    def stop(self):
        if not self.active:
            return
        print("\n>>> ⏹️  STREAMING GESTOPPT <<<\n")
        logger.info("Streaming stopped")
        self.active = False  # tells worker to drain & finish

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            self.stream = None

        if self.worker:
            self.worker.join(timeout=30)
            self.worker = None

        play_beep(STOP_BEEP_PATH)


# ─────────────────────── Keyboard handling ───────────────────────

def find_keyboard_devices():
    devices = []
    for path in list_devices():
        device = InputDevice(path)
        if ecodes.EV_KEY in device.capabilities():
            name = device.name.lower()
            if 'keyboard' in name or 'key' in name or 'at translated' in name:
                devices.append(device)
                logger.info(f"Found keyboard device: {device.path} - {device.name}")
                print(f"  ✓ {device.path} - {device.name}")
    if not devices:
        raise RuntimeError("No keyboard devices found!")
    return devices


alt_press_times = []
keyboard_lock = threading.Lock()
DOUBLE_TAP_TIMEOUT = 0.5

_transcriber = StreamingTranscriber()


def _toggle_streaming():
    if _transcriber.active:
        _transcriber.stop()
    else:
        _transcriber.start()


def monitor_device(device):
    try:
        logger.info(f"Monitoring device: {device.path}")
        print(f"✓ Listening on: {device.path} ({device.name})")
        for event in device.read_loop():
            if _shutdown_requested:
                break
            if event.type == ecodes.EV_KEY:
                key_event = evdev.categorize(event)
                if key_event.keycode in ['KEY_LEFTALT', 'KEY_RIGHTALT'] and key_event.keystate == 1:
                    with keyboard_lock:
                        now = time.time()
                        alt_press_times[:] = [t for t in alt_press_times if now - t < DOUBLE_TAP_TIMEOUT]
                        alt_press_times.append(now)
                        if len(alt_press_times) >= 2:
                            logger.info("*** DOUBLE-TAP DETECTED ***")
                            _toggle_streaming()
                            alt_press_times.clear()
    except OSError as e:
        if not _shutdown_requested:
            logger.warning(f"Device {device.path} lost ({e}), will rescan...")
    except Exception as e:
        logger.error(f"Error monitoring {device.path}: {e}")


def process_keyboard_events(devices):
    def start_threads(devs):
        ts = []
        for device in devs:
            t = threading.Thread(target=monitor_device, args=(device,), daemon=True)
            t.start()
            ts.append(t)
        return ts

    threads = start_threads(devices)
    active_paths = {d.path for d in devices}

    try:
        while not _shutdown_requested:
            time.sleep(5)
            if not _shutdown_requested and not any(t.is_alive() for t in threads):
                logger.warning("All keyboard threads died, rescanning devices...")
                try:
                    new_devices = find_keyboard_devices()
                    threads = start_threads(new_devices)
                    active_paths = {d.path for d in new_devices}
                except Exception as e:
                    logger.error(f"Rescan failed: {e}")
    except KeyboardInterrupt:
        pass

    logger.info("Exiting...")
    print("\n⏹️  Shutting down...")
    if _transcriber.active:
        try:
            _transcriber.stop()
        except Exception:
            pass
    for device in devices:
        try:
            device.close()
        except Exception:
            pass
    print("✓ Goodbye!")
    os._exit(0)


def _signal_handler(signum, frame):
    global _shutdown_requested
    print(f"\n⏹️  Received signal {signum}, shutting down...")
    _shutdown_requested = True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Echtzeit-Streaming-Transkription (Offline, Whisper) — tippt live am Cursor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Bedienung:
  Alt+Alt          Streaming starten
  Alt+Alt          Streaming stoppen
  Ctrl+C           Programm beenden

Funktionsweise:
  Während Sie sprechen, wird kontinuierlich transkribiert. An jeder kurzen
  Sprechpause wird die erkannte Phrase sofort an der Cursor-Position getippt
  (via wtype). Es wird NICHT auf das Ende der gesamten Eingabe gewartet.

Umgebungsvariablen:
  AUDIO_DEVICE          Input-Device Index (überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Device Index (für Beeps)
  WHISPER_MODEL         Modell (tiny/base/small/medium/large, Standard: small)
  STREAM_SILENCE_RMS    Schwelle Stille-Erkennung (Standard: 0.010)
  STREAM_MIN_SILENCE    Pausenlänge in s zum Phrasen-Ende (Standard: 0.7)
  STREAM_MIN_PHRASE     Minimale Phrasenlänge in s (Standard: 0.4)
  STREAM_MAX_PHRASE     Max. Phrasenlänge in s ohne Pause (Standard: 15.0)

Beispiele:
  ./run_streaming.sh                   Interaktive Geräteauswahl
  ./run_streaming.sh -a                Ein Gerät für Input + Output
  ./run_streaming.sh -d                Schnellstart mit Default-Geräten
  WHISPER_MODEL=tiny ./run_streaming.sh  Schnellstes Modell (geringste Latenz)
        """
    )
    parser.add_argument('-d', '--default', action='store_true',
                        help='Schnellstart: Default-Geräte ohne Auswahl-Menü')
    parser.add_argument('-a', '--auto', action='store_true',
                        help='Ein Gerät für Input UND Output auswählen')
    args = parser.parse_args()

    interactive = not args.default

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        get_whisper_model()
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        logger.error(f"Error loading Whisper model: {e}")
        sys.exit(1)

    try:
        if args.auto:
            select_auto_device()
        else:
            select_audio_device(interactive=interactive)
            try:
                select_output_device(interactive=interactive)
            except Exception as e:
                print(f"Error selecting output device: {e}")
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        sys.exit(1)

    if device_index is not None and output_device_index is not None:
        sd.default.device = [device_index, output_device_index]

    # Pick the 'type at cursor' backend (starts ydotoold if needed)
    detect_typer()
    if TYPER == 'clipboard':
        print("⚠️  Kein Live-Tippen verfügbar (ydotool/wtype nicht nutzbar).")
        print("    Text landet in der Zwischenablage — manuell mit Ctrl+V einfügen.")
        print("    Fix: sudo apt install ydotool  +  ydotoold-Daemon starten.\n")

    device_info = sd.query_devices(device_index)
    print("\n" + "=" * 60)
    print(f"🎤 AUDIO DEVICE: #{device_index} - {device_info['name']}")
    print(f"   Sample Rate: {samplerate} Hz (Streaming)")
    print(f"   Tippen am Cursor: {TYPER}")
    print(f"   VAD: Pause {MIN_SILENCE}s | Modell {os.environ.get('WHISPER_MODEL', 'small')}")
    print("=" * 60)

    try:
        print("\nDetecting keyboard devices...")
        keyboard_devices = find_keyboard_devices()
        print(f"\nFound {len(keyboard_devices)} keyboard device(s).")
        print("\nAlt+Alt zum Starten/Stoppen des Streamings. Ctrl+C zum Beenden.\n")
        process_keyboard_events(keyboard_devices)
    except PermissionError:
        print("ERROR: Need permission to access /dev/input devices!")
        print("Add user to 'input' group: sudo usermod -aG input $USER")
        logger.error("PermissionError: Cannot access /dev/input devices")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        logger.error(f"RuntimeError: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
        logger.error(f"Unexpected error: {e}")
