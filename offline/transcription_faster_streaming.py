#!/usr/bin/env python3
#
# transcription_faster_streaming.py — Echtes inkrementelles Streaming
#
# Im Gegensatz zur VAD-Phrasen-Version (transcription_streaming.py), die erst an
# einer Sprechpause eine ganze Phrase ausgibt, liefert diese Version Text
# WORTWEISE WÄHREND des Sprechens — auch mitten im Satz.
#
# Technik:
#   • faster-whisper (CTranslate2) — 3-4x schneller, weniger RAM als openai-whisper
#   • LocalAgreement-2 (Macháček et al., "whisper_streaming"): ein wachsender
#     Audio-Puffer wird wiederholt transkribiert; nur der Wort-Präfix, der über
#     ZWEI aufeinanderfolgende Läufe stabil bleibt, wird festgeschrieben und
#     getippt. So entsteht niedrige Latenz ohne ständig korrigierten Text.
#
# Getippt wird live an der Cursor-Position (ydotool/wtype/Clipboard, Wayland).

import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import re
import subprocess
import sys
import signal
import time
import logging
import torch
import evdev
from evdev import InputDevice, ecodes, list_devices
from faster_whisper import WhisperModel
import threading
import queue
import argparse

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

# Setup writable directory for logs
TRANSCRIPTION_DIR = os.path.expanduser("~/.transcription")
os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)

log_file_path = os.path.join(TRANSCRIPTION_DIR, "transcription_faster_streaming.log")

# Fixed 16 kHz mono float32 stream — Whisper's native format.
samplerate = 16000
BLOCKSIZE = 1600  # 0.1 s blocks

device_index = None         # Input device, selected at startup
output_device_index = None  # Output device (for beeps), selected at startup

# --- Streaming tuning (overridable via env) ---
# How much NEW audio to accumulate before re-running the model (= update cadence).
# ~2 s yields roughly 3-5 words per emit and gives the model enough CPU headroom
# to keep up with 'small'; lower it (e.g. 1.0) for snappier word-by-word output.
MIN_CHUNK = float(os.environ.get('STREAM_MIN_CHUNK', '2.0'))     # s
# Trim the working buffer once it grows past this (keeps the model fast).
MAX_BUFFER = float(os.environ.get('STREAM_MAX_BUFFER', '18.0'))  # s
# Beam size — 1 keeps latency low; higher = a bit more accurate but slower.
BEAM_SIZE = int(os.environ.get('STREAM_BEAM', '1'))

# Logger — file handler is verbose, console stays quiet so the live text is readable.
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logger.addHandler(console_handler)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)

_shutdown_requested = False
_model = None


def get_audio_device_from_env():
    """Get audio input device from environment variable or return None"""
    env_device = os.environ.get('AUDIO_DEVICE')
    if env_device:
        try:
            return int(env_device)
        except ValueError:
            return None
    return None


def get_model():
    """Load and cache the faster-whisper model on first call."""
    global _model
    if _model is None:
        name = os.environ.get('WHISPER_MODEL', 'small')
        name = {'large': 'large-v3'}.get(name, name)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        print(f"📥 Loading faster-whisper {name} ({device}/{compute}, one-time)...")
        logger.info(f"Loading faster-whisper {name} on {device}/{compute}")
        _model = WhisperModel(name, device=device, compute_type=compute)
        logger.info("faster-whisper ready")
        print(f"✓ faster-whisper {name} ready")
    return _model


# ─────────────────────────── Beeps ───────────────────────────

def _tone(frequencies, duration=0.2, volume=0.5):
    """Render one or more tones (a sequence of frequencies) as an int16 stereo array."""
    if not isinstance(frequencies, (list, tuple)):
        frequencies = [frequencies]
    sample_rate = 48000
    seg = duration / len(frequencies)
    parts = []
    for freq in frequencies:
        n = int(sample_rate * seg)
        t = np.linspace(0, seg, n, endpoint=False)
        env = np.minimum(1.0, np.minimum(t, seg - t) * 60)  # short fade in/out
        parts.append(np.sin(2 * np.pi * freq * t) * env * volume)
    waveform = (np.concatenate(parts) * 32767).astype(np.int16)
    return np.column_stack([waveform, waveform]), sample_rate


def _generate_beep_wav(filepath, frequency=1000, duration=0.2, volume=0.5):
    waveform_stereo, sample_rate = _tone(frequency, duration, volume)
    sf.write(filepath, waveform_stereo, sample_rate, subtype='PCM_16')


START_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "start_beep.wav")
STOP_BEEP_PATH = os.path.join(TRANSCRIPTION_DIR, "stop_beep.wav")
# Start: single rising blip. Stop: descending two-tone (900→500 Hz) — clearly distinct.
_generate_beep_wav(START_BEEP_PATH, frequency=800, duration=0.15, volume=0.5)
_generate_beep_wav(STOP_BEEP_PATH, frequency=[900, 500], duration=0.3, volume=0.5)


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

YDOTOOL_SOCKET = os.environ.get('YDOTOOL_SOCKET') or f"/run/user/{os.getuid()}/.ydotool_socket"
TYPER = None      # 'ydotool' | 'wtype' | 'clipboard'
KB_LAYOUT = 'us'  # active keyboard layout, set by detect_typer()

# ── ydotool layout fix ──────────────────────────────────────────────────────
# ydotool injects RAW Linux keycodes ("we're using raw keycodes now", its own
# --help) and assumes a US-QWERTY layout. On a German (QWERTZ) compositor that
# swaps Z↔Y and mangles umlauts/punctuation. `ydotool type` has no layout option.
# Fix: when the active layout is German, send the keycodes that produce the
# correct character ON THE GERMAN LAYOUT via `ydotool key` ourselves.
KEY_SHIFT, KEY_ALTGR = 42, 100

# char -> (Linux keycode, modifier or None) for the German T1 (de) layout
_DE_KEYMAP = {
    # number row
    '1': (2, None),  '!': (2, KEY_SHIFT),
    '2': (3, None),  '"': (3, KEY_SHIFT),
    '3': (4, None),  '§': (4, KEY_SHIFT),
    '4': (5, None),  '$': (5, KEY_SHIFT),
    '5': (6, None),  '%': (6, KEY_SHIFT),
    '6': (7, None),  '&': (7, KEY_SHIFT),
    '7': (8, None),  '/': (8, KEY_SHIFT),
    '8': (9, None),  '(': (9, KEY_SHIFT),
    '9': (10, None), ')': (10, KEY_SHIFT),
    '0': (11, None), '=': (11, KEY_SHIFT),
    'ß': (12, None), '?': (12, KEY_SHIFT),
    # top row
    'q': (16, None), 'Q': (16, KEY_SHIFT), '@': (16, KEY_ALTGR),
    'w': (17, None), 'W': (17, KEY_SHIFT),
    'e': (18, None), 'E': (18, KEY_SHIFT), '€': (18, KEY_ALTGR),
    'r': (19, None), 'R': (19, KEY_SHIFT),
    't': (20, None), 'T': (20, KEY_SHIFT),
    'z': (21, None), 'Z': (21, KEY_SHIFT),
    'u': (22, None), 'U': (22, KEY_SHIFT),
    'i': (23, None), 'I': (23, KEY_SHIFT),
    'o': (24, None), 'O': (24, KEY_SHIFT),
    'p': (25, None), 'P': (25, KEY_SHIFT),
    'ü': (26, None), 'Ü': (26, KEY_SHIFT),
    '+': (27, None), '*': (27, KEY_SHIFT),
    # home row
    'a': (30, None), 'A': (30, KEY_SHIFT),
    's': (31, None), 'S': (31, KEY_SHIFT),
    'd': (32, None), 'D': (32, KEY_SHIFT),
    'f': (33, None), 'F': (33, KEY_SHIFT),
    'g': (34, None), 'G': (34, KEY_SHIFT),
    'h': (35, None), 'H': (35, KEY_SHIFT),
    'j': (36, None), 'J': (36, KEY_SHIFT),
    'k': (37, None), 'K': (37, KEY_SHIFT),
    'l': (38, None), 'L': (38, KEY_SHIFT),
    'ö': (39, None), 'Ö': (39, KEY_SHIFT),
    'ä': (40, None), 'Ä': (40, KEY_SHIFT),
    '#': (43, None), "'": (43, KEY_SHIFT),
    # bottom row
    '<': (86, None), '>': (86, KEY_SHIFT),
    'y': (44, None), 'Y': (44, KEY_SHIFT),
    'x': (45, None), 'X': (45, KEY_SHIFT),
    'c': (46, None), 'C': (46, KEY_SHIFT),
    'v': (47, None), 'V': (47, KEY_SHIFT),
    'b': (48, None), 'B': (48, KEY_SHIFT),
    'n': (49, None), 'N': (49, KEY_SHIFT),
    'm': (50, None), 'M': (50, KEY_SHIFT),
    ',': (51, None), ';': (51, KEY_SHIFT),
    '.': (52, None), ':': (52, KEY_SHIFT),
    '-': (53, None), '_': (53, KEY_SHIFT),
    # whitespace
    ' ': (57, None), '\n': (28, None), '\t': (15, None),
}

# Fold typographic characters Whisper sometimes emits onto keys we can type.
_NORMALIZE = {
    '„': '"', '“': '"', '”': '"', '‚': "'", '‘': "'", '’': "'",
    '–': '-', '—': '-', '…': '...', ' ': ' ',
}


def detect_kb_layout():
    """Best-effort detection of the active keyboard layout (e.g. 'de', 'us')."""
    forced = os.environ.get('STREAM_KBLAYOUT')
    if forced:
        return forced.strip().lower()
    # GNOME active input source (most reliable on Wayland/Mutter)
    for key in ('mru-sources', 'sources'):
        try:
            r = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', key],
                capture_output=True, text=True, timeout=3)
            m = re.search(r"'xkb',\s*'([a-z]{2})", r.stdout)
            if m:
                return m.group(1)
        except Exception:
            pass
    # localectl fallback
    try:
        r = subprocess.run(['localectl', 'status'],
                           capture_output=True, text=True, timeout=3)
        m = re.search(r'X11 Layout:\s*(\w+)', r.stdout)
        if m:
            return m.group(1).split(',')[0].lower()
    except Exception:
        pass
    return 'us'


def _de_key_events(text):
    """Build a ydotool 'key' press/release sequence for `text` on the de layout.

    Returns a list like ['42:1', '21:1', '21:0', '42:0', ...]. Truly unmappable
    characters are skipped (logged) so typing always makes forward progress.
    """
    text = ''.join(_NORMALIZE.get(c, c) for c in text)
    seq = []
    for ch in text:
        m = _DE_KEYMAP.get(ch)
        if m is None:
            logger.warning(f"de-keymap: no key for {ch!r}, skipped")
            continue
        code, mod = m
        if mod:
            seq.append(f"{mod}:1")
        seq.append(f"{code}:1")
        seq.append(f"{code}:0")
        if mod:
            seq.append(f"{mod}:0")
    return seq


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
    global TYPER, KB_LAYOUT
    if ensure_ydotoold():
        TYPER = 'ydotool'
    elif _wtype_works():
        TYPER = 'wtype'
    else:
        TYPER = 'clipboard'
    KB_LAYOUT = detect_kb_layout()
    logger.info(f"Typing backend: {TYPER} (keyboard layout: {KB_LAYOUT})")
    return TYPER


def type_at_cursor(text):
    """Type text at the current cursor position using the detected backend.

    Called incrementally with small word-groups, so the clipboard fallback would
    overwrite previous words — there we accumulate and only the latest is pasteable.
    """
    if not text:
        return
    if TYPER == 'ydotool':
        # German layout: ydotool's raw US keycodes would swap Z/Y and mangle
        # umlauts — emit layout-correct keycodes via `ydotool key` instead.
        if KB_LAYOUT.startswith('de'):
            seq = _de_key_events(text)
            if seq:
                try:
                    subprocess.run(['ydotool', 'key', '-d', '2'] + seq,
                                   env=_ydotool_env(), check=True, timeout=30)
                    return
                except Exception as e:
                    logger.error(f"ydotool key error: {e}")
            else:
                return  # nothing typeable (only skipped chars)
        else:
            try:
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
    # Fallback: clipboard (manual paste) — append to the running line.
    try:
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(text.encode('utf-8'))
    except Exception as e:
        logger.error(f"Clipboard fallback failed: {e}")


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


# ─────────────────────── LocalAgreement streaming core ───────────────────────
#
# Port of the HypothesisBuffer / OnlineASRProcessor logic from
# whisper_streaming (Macháček, Dabre, Bojar 2023), trimmed to what we need.
# A word is only "committed" once it appears as the leading word in TWO
# consecutive transcription runs — giving stable, non-flickering output.

class HypothesisBuffer:
    def __init__(self):
        self.committed_in_buffer = []   # (start, end, word) already emitted
        self.buffer = []                # last run's still-unconfirmed tail
        self.new = []                   # current run's words
        self.last_committed_time = 0.0
        self.last_committed_word = None

    def insert(self, words, offset):
        # words: list of (start, end, text) relative to the current buffer start
        words = [(a + offset, b + offset, t) for a, b, t in words]
        self.new = [(a, b, t) for a, b, t in words if a > self.last_committed_time - 0.1]

        if self.new:
            a, b, t = self.new[0]
            if abs(a - self.last_committed_time) < 1.0 and self.committed_in_buffer:
                # Drop words whose n-gram was already committed (overlap from re-decoding).
                cn = len(self.committed_in_buffer)
                nn = len(self.new)
                for i in range(1, min(cn, nn, 5) + 1):
                    c = " ".join(self.committed_in_buffer[-j][2] for j in range(i, 0, -1))
                    tail = " ".join(self.new[j - 1][2] for j in range(1, i + 1))
                    if c == tail:
                        for _ in range(i):
                            self.new.pop(0)
                        break

    def flush(self):
        """Commit the longest common prefix of this run and the previous run."""
        commit = []
        while self.new and self.buffer:
            na, nb, nt = self.new[0]
            if nt == self.buffer[0][2]:
                commit.append((na, nb, nt))
                self.last_committed_word = nt
                self.last_committed_time = nb
                self.buffer.pop(0)
                self.new.pop(0)
            else:
                break
        self.buffer = self.new
        self.new = []
        self.committed_in_buffer.extend(commit)
        return commit

    def complete(self):
        """Return whatever is still un-committed (used on final stop)."""
        return self.buffer


class OnlineASRProcessor:
    def __init__(self, model):
        self.model = model
        self.audio_buffer = np.array([], dtype=np.float32)
        self.buffer_time_offset = 0.0
        self.hyp = HypothesisBuffer()

    def insert_audio_chunk(self, audio):
        self.audio_buffer = np.append(self.audio_buffer, audio)

    def _transcribe(self):
        segments, _info = self.model.transcribe(
            self.audio_buffer,
            language="de",
            task="transcribe",
            beam_size=BEAM_SIZE,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=True,
        )
        words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    words.append((w.start, w.end, w.word))
        return words

    def process_iter(self):
        """Run one transcription pass; return newly committed words (list of text)."""
        words = self._transcribe()
        self.hyp.insert(words, self.buffer_time_offset)
        committed = self.hyp.flush()

        # Keep the working buffer bounded: once it is long, drop everything up to
        # the last committed word so the model stays fast.
        buf_len = len(self.audio_buffer) / samplerate
        if buf_len > MAX_BUFFER and self.hyp.last_committed_time > self.buffer_time_offset:
            cut = self.hyp.last_committed_time - self.buffer_time_offset
            cut_samples = int(cut * samplerate)
            self.audio_buffer = self.audio_buffer[cut_samples:]
            self.buffer_time_offset = self.hyp.last_committed_time

        return [t for _a, _b, t in committed]

    def finish(self):
        """Final pass on stop: transcribe whatever audio is still buffered and
        commit ALL words not yet emitted, so the tail of speech is never cut off.

        During streaming LocalAgreement only commits words stable across two runs,
        which leaves the last ~chunk of speech un-emitted. Here there is no "next
        run" to agree with, so the final transcription is taken as authoritative.
        """
        if len(self.audio_buffer) == 0:
            return [t for _a, _b, t in self.hyp.complete()]

        words = self._transcribe()
        # insert() drops words already committed (time + n-gram overlap dedup),
        # leaving self.hyp.new = exactly the still-uncommitted tail.
        self.hyp.insert(words, self.buffer_time_offset)
        final = list(self.hyp.new) or list(self.hyp.buffer)
        if final:
            self.hyp.committed_in_buffer.extend(final)
            self.hyp.last_committed_time = final[-1][1]
        self.hyp.buffer = []
        self.hyp.new = []
        return [t for _a, _b, t in final]


# ─────────────────────── Streaming transcriber ───────────────────────

class FasterStreamingTranscriber:
    """Continuously records and emits text word-by-word via LocalAgreement."""

    def __init__(self):
        self.q = queue.Queue()
        self.active = False
        self.stream = None
        self.worker = None
        self._first_emit = True

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio status: {status}")
        self.q.put(indata[:, 0].copy())

    def _emit(self, words):
        if not words:
            return
        text = "".join(words)
        if self._first_emit:
            text = text.lstrip()   # avoid a leading space at the cursor
            self._first_emit = False
        if not text:
            return
        print(text, end="", flush=True)
        type_at_cursor(text)

    def _worker(self):
        online = OnlineASRProcessor(get_model())
        since_last = 0
        chunk_samples = int(MIN_CHUNK * samplerate)

        while self.active or not self.q.empty():
            try:
                block = self.q.get(timeout=0.1)
                online.insert_audio_chunk(block)
                since_last += len(block)
            except queue.Empty:
                pass

            if since_last >= chunk_samples and len(online.audio_buffer) > 0:
                try:
                    self._emit(online.process_iter())
                except Exception as e:
                    logger.error(f"process_iter error: {e}")
                since_last = 0

        # final flush
        try:
            self._emit(online.finish())
        except Exception as e:
            logger.error(f"finish error: {e}")
        print()  # newline after the streamed line

    def start(self):
        if self.active:
            return
        self.active = True
        self._first_emit = True
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

        play_beep(START_BEEP_PATH)
        print("\n>>> 🔴 STREAMING GESTARTET <<<")
        print("🎤 Sprechen Sie — Text erscheint wortweise am Cursor. Alt+Alt zum Stoppen.\n")
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
        self.active = False

        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.warning(f"Error closing stream: {e}")
            self.stream = None

        if self.worker:
            self.worker.join(timeout=60)
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

_transcriber = FasterStreamingTranscriber()


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

    try:
        while not _shutdown_requested:
            time.sleep(5)
            if not _shutdown_requested and not any(t.is_alive() for t in threads):
                logger.warning("All keyboard threads died, rescanning devices...")
                try:
                    new_devices = find_keyboard_devices()
                    threads = start_threads(new_devices)
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
        description="Echtes inkrementelles Streaming (faster-whisper + LocalAgreement) — tippt wortweise live am Cursor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Bedienung:
  Alt+Alt          Streaming starten
  Alt+Alt          Streaming stoppen
  Ctrl+C           Programm beenden

Funktionsweise:
  Ein wachsender Audio-Puffer wird ~jede Sekunde mit faster-whisper neu
  transkribiert. Nur Wörter, die über ZWEI Läufe stabil bleiben (LocalAgreement),
  werden festgeschrieben und sofort getippt. So erscheint Text WÄHREND des
  Sprechens — auch mitten im Satz, nicht erst an der Sprechpause.

Umgebungsvariablen:
  AUDIO_DEVICE          Input-Device Index (überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Device Index (für Beeps)
  WHISPER_MODEL         Modell (tiny/base/small/medium/large, Standard: small)
  STREAM_MIN_CHUNK      Update-Takt in s (~2s ≈ 3-5 Wörter pro Schub, Standard: 2.0)
  STREAM_MAX_BUFFER     Puffer-Obergrenze in s vor Beschnitt (Standard: 18.0)
  STREAM_BEAM           Beam-Size (1 = schnellste Latenz, Standard: 1)

Tipp:
  Bei Standard-Takt (2s, ~3-5 Wörter pro Schub) hält 'small' auch auf CPU Schritt.
  Für möglichst wortweise Ausgabe Takt senken und kleineres Modell wählen:
    STREAM_MIN_CHUNK=1.0 WHISPER_MODEL=base ./run_faster_streaming.sh
    STREAM_MIN_CHUNK=1.0 WHISPER_MODEL=tiny ./run_faster_streaming.sh

Beispiele:
  ./run_faster_streaming.sh                  Interaktive Geräteauswahl
  ./run_faster_streaming.sh -a               Ein Gerät für Input + Output
  ./run_faster_streaming.sh -d               Schnellstart mit Default-Geräten
  WHISPER_MODEL=tiny ./run_faster_streaming.sh   Geringste Latenz
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
        get_model()
    except Exception as e:
        print(f"Error loading model: {e}")
        logger.error(f"Error loading model: {e}")
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

    detect_typer()
    if TYPER == 'clipboard':
        print("⚠️  Kein Live-Tippen verfügbar (ydotool/wtype nicht nutzbar).")
        print("    Im Streaming-Modus ist der Clipboard-Fallback ungeeignet")
        print("    (jedes Wort überschreibt das vorige). Fix: sudo apt install ydotool\n")

    device_info = sd.query_devices(device_index)
    print("\n" + "=" * 60)
    print(f"🎤 AUDIO DEVICE: #{device_index} - {device_info['name']}")
    print(f"   Sample Rate: {samplerate} Hz (faster-whisper Streaming)")
    print(f"   Tippen am Cursor: {TYPER}")
    print(f"   Update-Takt: {MIN_CHUNK}s | Modell: {os.environ.get('WHISPER_MODEL', 'small')} | Beam: {BEAM_SIZE}")
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
