#!/usr/bin/env python3

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
import warnings
# CPU-Betrieb: Whisper nutzt FP32 statt FP16 — die Warnung ist erwartbar, kein Fehler.
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")
import whisper
import torch
# Whisper würde sonst alle CPU-Kerne belegen und den Audio-Callback-Thread
# (muss sein Zeitfenster einhalten, sonst Sample-Verlust) unter Last verdrängen.
torch.set_num_threads(max(2, min(4, os.cpu_count() or 4)))
import evdev
from evdev import InputDevice, ecodes, list_devices
import threading
import queue
import argparse

import _typer  # gemeinsames Tipp-Backend (ydotool/wtype/Clipboard)

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

# Aufnahme wird nach dieser Dauer automatisch gestoppt und transkribiert —
# verhindert endlose Aufnahmen, wenn der Stopp-Doppeltipp nicht ankommt.
MAX_RECORDING_SECONDS = 120
_max_duration_timer = None

# Sprechpause länger als RECORD_SILENCE_STOP s → Aufnahme automatisch stoppen
# und transkribieren (0 = aus). Stille-Schwelle wie im Streaming-Modus.
RECORD_SILENCE_STOP = float(os.environ.get('RECORD_SILENCE_STOP', '15.0'))
RECORD_SILENCE_RMS = float(os.environ.get('STREAM_SILENCE_RMS', '0.010'))
_silence_run = 0.0
_silence_stop_fired = False

# ── Live-Pipelining (OFFLINE_LIVE) ───────────────────────────────────────────
# Standard ist klassisch: aufnehmen → stoppen → die GANZE Aufnahme am Stück
# transkribieren. Optional (OFFLINE_LIVE=1) läuft während der Aufnahme ein
# Hintergrund-Worker mit: er segmentiert an Sprechpausen (VAD) und
# transkribiert/tippt jede fertige Phrase sofort. Das Live-Tippen zerlegt das
# Diktat aber in Phrasen-Häppchen — deshalb bewusst opt-in.
_live_mode = os.environ.get('OFFLINE_LIVE', '0') != '0'
# VAD-/Segment-Tuning (teilt sich die Schwellen mit dem Streaming-Modus).
LIVE_MIN_SILENCE = float(os.environ.get('STREAM_MIN_SILENCE', '0.7'))  # s Pause → Phrasen-Ende
LIVE_MIN_PHRASE = float(os.environ.get('STREAM_MIN_PHRASE', '0.4'))    # s min. Phrase zum Transkribieren
LIVE_MAX_PHRASE = float(os.environ.get('STREAM_MAX_PHRASE', '15.0'))   # s Force-Flush langer Phrase
# Whisper wurde auf Untertitel-Korpora trainiert und gibt auf Stille/Rauschen
# deren Abspänne aus ("Untertitel: SWR 2020", "Vielen Dank."). Zwei Filter:
# no_speech_prob des Segments und ein Textabgleich gegen bekannte Artefakte.
LIVE_NO_SPEECH_MAX = float(os.environ.get('STREAM_NO_SPEECH_MAX', '0.6'))
_SENDER = r'(?:swr|zdf|ard|br|wdr|ndr|mdr|rbb|orf|3sat|arte|srf|zdf\.de|amara\.org)'
_FUELL = r'(?:im|auftrag|von|des|der|die|und|f(?:ü|u)r|mit|by|the|community)'
# Abspann-Zeile: startet mit "Untertitel…" oder einem Sender und besteht sonst
# nur noch aus Füllwörtern, Sendernamen und Jahreszahl.
_ABSPANN = (
    r'(?:untertitel(?:ung)?|' + _SENDER + r')\b'
    r'(?:[\s:,.\-]+(?:' + _FUELL + r'|' + _SENDER + r'|\d{4}))*'
)
# Harte Artefakte: Abspann-/Copyright-Zeilen und reine Satzzeichen. Die
# diktiert niemand — immer verwerfen.
_HALLUCINATION_HARD_RE = re.compile(
    r'^(?:'
    + _ABSPANN +
    r'|copyright\b(?:[\s:,.\-]+(?:' + _FUELL + r'|' + _SENDER + r'|\d{4}))*'
    r'|(?:vielen\s+)?dank(?:e)?\s+f(?:ü|u)r(?:s)?\s+(?:zuschauen|zusehen|die\s+aufmerksamkeit)'
    r'|(?:[.,!?\-\s…«»*])+'
    r')[\s.!?,\-–—…*]*$',
    re.IGNORECASE,
)
# Mehrdeutig: häufige Halluzination, aber genauso echtes Diktat ("Vielen Dank."
# am Mail-Ende). Nur verwerfen, wenn Whisper ohnehin Zweifel an Sprache hat.
_HALLUCINATION_SOFT_RE = re.compile(
    r'^(?:'
    r'(?:vielen\s+)?dank(?:e)?'
    r'|bis\s+zum\s+n(?:ä|a)chsten\s+mal'
    r'|tsch(?:ü|u)ss|hallo|ja|ok(?:ay)?|so'
    r')[\s.!?,\-–—…*]*$',
    re.IGNORECASE,
)
# Ab hier gilt eine mehrdeutige Phrase als Halluzination (unter dem harten
# LIVE_NO_SPEECH_MAX, sonst hätte die Stufe keine Wirkung).
LIVE_NO_SPEECH_SOFT = float(os.environ.get('STREAM_NO_SPEECH_SOFT', '0.25'))


def _is_hallucination(text, no_speech=0.0):
    """True, wenn der Text ein Whisper-Stille-Artefakt ist.

    Harte Abspann-Muster fliegen immer raus; mehrdeutige Kurzphrasen nur, wenn
    no_speech_prob zusätzlich gegen echte Sprache spricht."""
    stripped = text.strip()
    if not stripped:
        return True
    if _HALLUCINATION_HARD_RE.match(stripped):
        return True
    return bool(
        no_speech >= LIVE_NO_SPEECH_SOFT and _HALLUCINATION_SOFT_RE.match(stripped)
    )
_live_q = queue.Queue()   # float32-Blöcke aus dem Audio-Callback an den Live-Worker
_live_pump = None         # aktueller Live-Worker-Thread

# Serialisiert die Transkriptions-Worker (Whisper ist nicht thread-safe;
# Reihenfolge der getippten Ausgabe bleibt erhalten).
_transcribe_lock = threading.Lock()

# Feste 16-kHz-Mono-float32-Aufnahme — Whispers natives Format. PipeWire/
# PulseAudio resampelt das Gerät transparent; so sind die Live-Segmente ohne
# Umrechnung direkt whisper-tauglich und die gespeicherte WAV ist sprach-ideal.
samplerate = 16000
BLOCKSIZE = 1600  # 0.1-s-Blöcke → feine Auflösung für die Pausenerkennung
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
    """Play a WAV file via paplay (PipeWire/PulseAudio - no ALSA conflicts)"""
    try:
        subprocess.run(['paplay', filepath], timeout=2, check=True)
    except FileNotFoundError:
        # Fallback to sounddevice if paplay not available
        try:
            data, fs = sf.read(filepath, dtype='int16')
            sd.play(data, fs, device=output_device_index, blocking=True)
            sd.stop()
        except Exception as e:
            logger.warning(f"Could not play sound: {e}")
    except Exception as e:
        logger.warning(f"Could not play sound via paplay: {e}")

def play_beep_async(filepath):
    """Beep im Hintergrund — paplay blockiert sonst bis zu 2s den Aufrufer
    (Tastatur-Thread!) und die Aufnahme würde verzögert starten/stoppen."""
    threading.Thread(target=play_beep, args=(filepath,), daemon=True).start()

def play_start_recording_sound():
    """Play sound when recording starts"""
    play_beep_async(START_BEEP_PATH)

def play_stop_recording_sound():
    """Play sound when recording stops"""
    play_beep_async(STOP_BEEP_PATH)

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

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[1]), 0)
    while True:
        try:
            choice = input(f"Select OUTPUT device for beeps [0-{len(devices_list)-1}], Enter=Default: ").strip()
            if choice == "":
                choice_idx = default_list_idx
            else:
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
            print("Invalid selection!")

# Select single device for both input and output
def select_auto_device(interactive=False):
    """Select ONE device for both input and output"""
    global device_index, output_device_index

    devices_list = []
    all_devices = sd.query_devices()

    for idx, device in enumerate(all_devices):
        if device['max_input_channels'] > 0 and device['max_output_channels'] > 0:
            devices_list.append(idx)

    if len(devices_list) == 0:
        raise RuntimeError("No devices with both input and output found!")

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[0]), 0)

    # Non-interactive mode (systemd service ODER Auto-Restart mit -d): keine
    # Rückfrage — automatisch das Default-Gerät nehmen.
    import sys
    if not interactive or not sys.stdin.isatty():
        choice_idx = default_list_idx
        device_index = devices_list[choice_idx]
        output_device_index = devices_list[choice_idx]
        selected_name = all_devices[device_index]['name']
        print(f"✓ Auto-selected default device: {selected_name} (Input + Output)\n")
        logger.info(f"Auto-selected device {device_index} for both input and output: {selected_name}")
        return device_index

    print("\n=== SELECT DEVICE FOR INPUT + OUTPUT ===\n")
    for i, idx in enumerate(devices_list):
        device = all_devices[idx]
        is_default = " ← DEFAULT" if idx == sd.default.device[0] else ""
        print(f"[{i}] Device #{idx}: {device['name']}{is_default}")
        print(f"         Input: {device['max_input_channels']}ch, Output: {device['max_output_channels']}ch, Rate: {device['default_samplerate']} Hz")
    print()

    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}], Enter=Default: ").strip()
            if choice == "":
                choice_idx = default_list_idx
            else:
                choice_idx = int(choice)
            if choice_idx < 0 or choice_idx >= len(devices_list):
                print("Invalid selection!")
                continue
            device_index = devices_list[choice_idx]
            output_device_index = devices_list[choice_idx]
            selected_name = all_devices[device_index]['name']
            print(f"\n✓ Using: {selected_name} (Input + Output)\n")
            logger.info(f"Selected device {device_index} for both input and output: {selected_name}")
            return device_index
        except ValueError:
            print("Invalid selection!")

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

    default_list_idx = next((i for i, d in enumerate(devices_list) if d == sd.default.device[0]), 0)
    while True:
        try:
            choice = input(f"Select device [0-{len(devices_list)-1}], Enter=Default: ").strip()
            if choice == "":
                choice_idx = default_list_idx
            else:
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
            print("Invalid selection!")

# Keyboard device detection
def find_keyboard_devices(log=True):
    devices = []
    for path in list_devices():
        try:
            device = InputDevice(path)
        except OSError:
            # Gerät verschwand zwischen list_devices() und open() (Hotplug-Race)
            continue
        if ecodes.EV_KEY in device.capabilities():
            if 'keyboard' in device.name.lower() or 'key' in device.name.lower() or 'at translated' in device.name.lower():
                devices.append(device)
                if log:
                    logger.info(f"Found keyboard device: {device.path} - {device.name}")
                    print(f"  ✓ {device.path} - {device.name}")
            else:
                device.close()
        else:
            device.close()

    if not devices and log:
        raise RuntimeError("No keyboard devices found!")

    return devices


def _on_max_duration_reached():
    """Auto-Stopp: MAX_RECORDING_SECONDS erreicht → stoppen und transkribieren."""
    if recording:
        msg = f"⏱️  Max. Aufnahmedauer ({MAX_RECORDING_SECONDS}s) erreicht — Aufnahme wird gestoppt"
        logger.info(msg)
        print(f"\n>>> {msg} <<<\n")
        stop_recording()


def _start_max_duration_timer():
    global _max_duration_timer
    _cancel_max_duration_timer()
    _max_duration_timer = threading.Timer(MAX_RECORDING_SECONDS, _on_max_duration_reached)
    _max_duration_timer.daemon = True
    _max_duration_timer.start()


def _cancel_max_duration_timer():
    global _max_duration_timer
    if _max_duration_timer is not None:
        _max_duration_timer.cancel()
        _max_duration_timer = None


def _on_silence_stop():
    """Auto-Stopp: Sprechpause > RECORD_SILENCE_STOP s → stoppen und transkribieren."""
    if recording:
        msg = f"💤 Sprechpause > {RECORD_SILENCE_STOP:.0f}s — Aufnahme wird gestoppt"
        logger.info(msg)
        print(f"\n>>> {msg} <<<\n")
        stop_recording()


def audio_callback(indata, frames, time, status):
    """Callback to capture audio data (16 kHz mono float32)."""
    global audio_data, recording, _silence_run, _silence_stop_fired
    if status:
        # PortAudio-Overflow/Underflow — meist ein Zeichen, dass der Audio-Thread
        # unter CPU-Last sein Zeitfenster verpasst hat (verlorene/verzerrte Samples).
        logger.warning(f"Audio status: {status}")
    if recording:
        # Kanal 0 als 1-D-float32; deckt Mono und (Fallback-)Mehrkanal ab.
        block = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        audio_data.append(block)
        # Live-Worker parallel füttern → transkribiert Phrasen schon während der Aufnahme.
        if _live_mode:
            _live_q.put(block)
        if RECORD_SILENCE_STOP > 0 and not _silence_stop_fired:
            rms = float(np.sqrt(np.mean(block ** 2)))
            if rms >= RECORD_SILENCE_RMS:
                _silence_run = 0.0
            else:
                _silence_run += frames / float(samplerate)
                if _silence_run >= RECORD_SILENCE_STOP:
                    # stop_recording() schließt den Stream → nie direkt aus dem
                    # PortAudio-Callback aufrufen, sonst Deadlock.
                    _silence_stop_fired = True
                    threading.Thread(target=_on_silence_stop, daemon=True).start()

def _start_live_pump():
    """Startet den Hintergrund-Worker, der schon während der Aufnahme Phrasen
    transkribiert und tippt. No-op, wenn OFFLINE_LIVE=0."""
    global _live_pump
    if not _live_mode:
        return
    # Alte Blöcke aus einer vorherigen Aufnahme verwerfen.
    while not _live_q.empty():
        try:
            _live_q.get_nowait()
        except queue.Empty:
            break
    _live_pump = threading.Thread(target=_live_worker, daemon=True)
    _live_pump.start()


def start_recording():
    global recording, audio_data, input_stream, _silence_run, _silence_stop_fired
    if not recording:
        device_info = sd.query_devices(device_index)
        device_name = device_info['name']

        mode = "live (Phrasen während der Aufnahme)" if _live_mode else "klassisch (am Ende)"
        msg = f"🎤 Recording from DEVICE {device_index}: {device_name} @ {samplerate}Hz mono — {mode}"
        logger.info(msg)
        print(msg)

        # Set recording flag FIRST to prevent re-entry during beep
        recording = True
        audio_data = []
        _silence_run = 0.0
        _silence_stop_fired = False

        play_start_recording_sound()

        try:
            input_stream = sd.InputStream(
                device=device_index,
                samplerate=samplerate,
                channels=1,
                dtype='float32',
                blocksize=BLOCKSIZE,
                callback=audio_callback
            )
            input_stream.start()
            logger.info("InputStream started")
            _start_max_duration_timer()
            _start_live_pump()
        except Exception as e:
            logger.error(f"Error starting input stream: {e}")
            recording = False
            # Try fallback to default device
            try:
                logger.info("Trying fallback to default input device...")
                input_stream = sd.InputStream(
                    samplerate=samplerate,
                    channels=1,
                    dtype='float32',
                    blocksize=BLOCKSIZE,
                    callback=audio_callback
                )
                input_stream.start()
                recording = True
                logger.info("Fallback InputStream started")
                _start_max_duration_timer()
                _start_live_pump()
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                recording = False

def stop_recording():
    """Stoppt die Aufnahme SOFORT und gibt den Aufrufer frei.

    Wichtig: diese Funktion läuft im evdev-Thread der Tastatur. Whisper hier
    synchron laufen zu lassen blockiert das Einlesen der Tastatur-Events für die
    Dauer der Transkription (Sekunden bis Minuten) — dann kommt der nächste
    Alt-Doppeltipp nicht an und das Tool wirkt eingefroren. Deshalb: Stream
    schließen, Audio übernehmen, Transkription an einen Worker-Thread übergeben.
    """
    global recording, audio_data, input_stream, _live_pump
    if recording:
        logger.info("Recording stopped...")
        print(">>> ⏹️ RECORDING STOPPED <<<\n")
        recording = False
        _cancel_max_duration_timer()
        play_stop_recording_sound()

        if input_stream:
            input_stream.stop()
            input_stream.close()
            input_stream = None

        chunks, audio_data = audio_data, []

        if not chunks:
            logger.warning("No audio data recorded")
            print("⚠️  No audio data recorded")
            return

        msg = f"✓ Recording completed: {sum(len(d) for d in chunks)} samples"
        logger.info(msg)
        print(msg)

        if _live_mode:
            # Der Live-Worker hat die Phrasen schon während der Aufnahme getippt.
            # Nur noch: auf den finalen Tail-Flush warten und die volle WAV
            # sichern — beides im Hintergrund, damit der Tastatur-Thread frei bleibt.
            pump, _live_pump = _live_pump, None
            threading.Thread(
                target=_finish_live,
                args=(pump, chunks, samplerate),
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=_process_recording,
                args=(chunks, samplerate),
                daemon=True,
            ).start()


def _process_recording(chunks, rate):
    """Worker (klassisch, OFFLINE_LIVE=0): Aufnahme speichern, komplett
    transkribieren, tippen. Läuft NIE im Tastatur-Thread. Das Lock serialisiert
    parallele Aufnahmen — Whisper ist nicht thread-safe und die Ausgabe soll in
    der richtigen Reihenfolge landen."""
    with _transcribe_lock:
        path = save_audio(chunks, rate)
        if path:
            # Argumentlos aufrufen: abgeleitete Modi (z.B. claude) ersetzen
            # transcribe_and_output durch eine argumentlose Variante, die
            # base.file_path liest. save_audio() hat genau dorthin geschrieben.
            transcribe_and_output()


def _finish_live(pump, chunks, rate):
    """Worker (Live-Modus): wartet auf den letzten Phrasen-Flush des Live-Workers
    und speichert dann die volle Aufnahme. Es wird NICHT erneut alles am Stück
    transkribiert — das haben die Live-Phrasen bereits erledigt."""
    if pump is not None:
        pump.join(timeout=120)
    save_audio(chunks, rate)
    print("✓ Live-Transkription abgeschlossen")


def save_audio(chunks, rate):
    """Schreibt die Aufnahme und liefert den Pfad (None bei Fehler)."""
    try:
        if not chunks:
            logger.warning("No audio data to save.")
            return None

        audio_array = np.concatenate(chunks, axis=0)
        sf.write(file_path, audio_array, samplerate=rate, subtype='PCM_16')
        logger.info(f"Audio saved to {file_path} ({len(audio_array)} samples)")
        print(f"✓ Audio saved to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving audio: {e}")
        print(f"✗ Error saving audio: {e}")
        return None


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

    except OSError as e:
        if not _shutdown_requested:
            global _restart_requested
            logger.warning(f"Device {device.path} lost ({e}), restarting with default settings...")
            _restart_requested = True
    except Exception as e:
        logger.error(f"Error monitoring {device.path}: {e}")

_shutdown_requested = False
_restart_requested = False

# Exit-Code, den die Wrapper/systemd als "Eingabegerät verloren → mit
# Default-Einstellungen (nicht-interaktiv) neu starten" interpretieren.
RESTART_EXIT_CODE = 75

# Wie lange (Sekunden) ohne EINE einzige Tastatur gewartet wird, bevor als
# letzter Ausweg ein kompletter Neustart (exit 75) ausgelöst wird. Solange noch
# mindestens ein Keyboard überwacht wird, wird NIE neu gestartet — verlorene
# Geräte werden entfernt, wiederkehrende/neue per Hotplug automatisch aufgenommen.
NO_KEYBOARD_GRACE_S = 30
# Takt der Hotplug-/Liveness-Prüfung.
RESCAN_INTERVAL_S = 3

def process_keyboard_events(devices):
    global _shutdown_requested, _restart_requested, recording

    # path -> (InputDevice, Thread)
    active = {}
    for device in devices:
        t = threading.Thread(target=monitor_device, args=(device,), daemon=True)
        t.start()
        active[device.path] = (device, t)

    empty_since = None  # monotonic-Zeitpunkt, seit dem KEINE Tastatur mehr da ist

    try:
        while not _shutdown_requested:
            time.sleep(RESCAN_INTERVAL_S)
            if _shutdown_requested:
                break

            # 1) Verlorene Geräte (Thread beendet via OSError) entfernen ────────
            for path in list(active.keys()):
                dev, t = active[path]
                if not t.is_alive():
                    logger.warning(f"Tastatur verschwunden: {path} — entfernt, warte auf Wiederkehr")
                    try:
                        dev.close()
                    except Exception:
                        pass
                    del active[path]
            _restart_requested = False  # Signal verbraucht — kein harter Restart mehr

            # 2) Neu aufgetauchte / wiederverbundene Tastaturen aufnehmen ───────
            try:
                current = find_keyboard_devices(log=False)
            except Exception:
                current = []
            for dev in current:
                if dev.path in active:
                    try:
                        dev.close()  # bereits überwacht — Duplikat schließen
                    except Exception:
                        pass
                    continue
                t = threading.Thread(target=monitor_device, args=(dev,), daemon=True)
                t.start()
                active[dev.path] = (dev, t)
                logger.info(f"Neue Tastatur erkannt — überwache jetzt: {dev.path} - {dev.name}")
                print(f"  ✓ (hotplug) {dev.path} - {dev.name}")

            # 3) Total-Verlust: erst nach Grace-Periode neu starten ─────────────
            if not active:
                if empty_since is None:
                    empty_since = time.monotonic()
                    logger.warning("Keine Tastatur mehr aktiv — warte auf Wiederkehr...")
                elif time.monotonic() - empty_since > NO_KEYBOARD_GRACE_S:
                    logger.warning(
                        f"Keine Tastatur nach {NO_KEYBOARD_GRACE_S}s zurück — Neustart mit "
                        f"Default-Einstellungen (exit {RESTART_EXIT_CODE})."
                    )
                    print("\n🔁 Eingabegerät verloren — Neustart mit Default-Einstellungen...")
                    if recording:
                        try:
                            stop_recording()
                        except Exception:
                            pass
                    os._exit(RESTART_EXIT_CODE)
            else:
                empty_since = None
    except KeyboardInterrupt:
        pass

    # Clean shutdown
    logger.info("Exiting...")
    print("\n⏹️  Shutting down...")
    if recording:
        try:
            stop_recording()
        except Exception:
            pass
    # Close all input devices
    for dev, _t in list(active.values()):
        try:
            dev.close()
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

        transcription = _typer.strip_auto_periods(result["text"])
        logging.info(f"Transcription result: {transcription}")

        return transcription

    except Exception as e:
        logging.error(f"Failed to transcribe audio with Whisper: {e}")
        raise

def transcribe_array(audio_float32):
    """Transkribiert ein float32-Mono-16-kHz-Array direkt aus dem Speicher
    (ohne Umweg über eine Datei) und liefert (Text, no_speech_prob).

    no_speech_prob ist das Maximum über alle Segmente: schlägt eines an, war
    in der Phrase mit hoher Wahrscheinlichkeit gar keine Sprache."""
    if audio_float32 is None or len(audio_float32) == 0:
        return "", 1.0
    try:
        model = get_whisper_model()
        result = model.transcribe(
            audio_float32,
            language="de",
            task="transcribe",
            fp16=torch.cuda.is_available(),
            verbose=False,
        )
        segments = result.get("segments") or []
        no_speech = max((s.get("no_speech_prob", 0.0) for s in segments), default=0.0)
        return _typer.strip_auto_periods(result["text"].strip()), no_speech
    except Exception as e:
        logger.error(f"Live-Transkription fehlgeschlagen: {e}")
        return "", 1.0


def _flush_live(seg, seg_samples):
    """Transkribiert eine fertige Phrase und tippt sie sofort an den Cursor."""
    if seg_samples < LIVE_MIN_PHRASE * samplerate:
        return
    audio = np.concatenate(seg).astype(np.float32)
    with _transcribe_lock:
        text, no_speech = transcribe_array(audio)
    if not text:
        return
    dur = seg_samples / samplerate
    if no_speech >= LIVE_NO_SPEECH_MAX:
        logger.info(f"Verworfen ({dur:.1f}s, no_speech={no_speech:.2f}) → {text!r}")
        return
    if _is_hallucination(text, no_speech):
        logger.info(f"Verworfen (Artefakt, {dur:.1f}s, no_speech={no_speech:.2f}) → {text!r}")
        return
    logger.info(f"Live-Phrase ({dur:.1f}s, no_speech={no_speech:.2f}) → {text!r}")
    print(f"📝 {text}")
    _typer.type_at_cursor(text + " ")


def _live_worker():
    """Läuft während der Aufnahme: konsumiert Audio-Blöcke, segmentiert an
    Sprechpausen (VAD) und tippt jede fertige Phrase sofort. Bricht nach dem
    Stoppen ab, sobald die Queue leer ist, und flusht den letzten Rest."""
    seg = []
    seg_samples = 0
    silence_run = 0.0
    in_speech = False
    block_dur = BLOCKSIZE / samplerate

    while recording or not _live_q.empty():
        try:
            block = _live_q.get(timeout=0.1)
        except queue.Empty:
            continue

        rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0
        voiced = rms >= RECORD_SILENCE_RMS

        if voiced:
            in_speech = True
            seg.append(block)
            seg_samples += len(block)
            silence_run = 0.0
        elif in_speech:
            # Nachlaufende Stille behalten und die Pause zählen.
            seg.append(block)
            seg_samples += len(block)
            silence_run += block_dur
            if silence_run >= LIVE_MIN_SILENCE:
                _flush_live(seg, seg_samples)
                seg, seg_samples, silence_run, in_speech = [], 0, 0.0, False
        # sonst: führende Stille vor jeder Sprache → verwerfen

        # Sehr lange Phrasen ohne Pause zwangsweise flushen.
        if seg_samples >= LIVE_MAX_PHRASE * samplerate:
            _flush_live(seg, seg_samples)
            seg, seg_samples, silence_run, in_speech = [], 0, 0.0, False

    # Letzter Rest beim Stoppen.
    if seg_samples > 0:
        _flush_live(seg, seg_samples)


def type_text_in_active_window(text):
    """Type text directly at the cursor position (Wayland).

    Uses the shared typing backend (ydotool → wtype → clipboard fallback),
    so the transcription appears wherever the cursor is — no manual Ctrl+V.
    """
    print(f"\n⌨️  Typing {len(text)} characters at cursor ({_typer.TYPER})...")
    logger.info(f"Typing at cursor ({_typer.TYPER}): {text}")
    _typer.type_at_cursor(text)
    print("✓ Text getippt")


def transcribe_and_output(audio_path=None):
    if audio_path is None:
        audio_path = file_path
    try:
        # Hinweis auf Start der Transkription
        print("Starting transcription...")
        logging.info("Starting transcription...")

        transcription = transcribe_with_whisper(audio_path)

        if not transcription or transcription.strip() == "":
            print("No valid transcription found.")
            logging.info("No valid transcription generated.")
            return

        # Bestand die ganze Aufnahme nur aus einem Whisper-Stille-Artefakt
        # ("Untertitel: SWR 2020"), nichts tippen. no_speech ist hier unbekannt
        # → nur die harten Muster greifen.
        if _is_hallucination(transcription):
            logging.info(f"Verworfen (Artefakt) → {transcription!r}")
            print("No valid transcription found.")
            return

        # Transkription ausgeben und ins aktive Fenster eingeben
        print(f"Transcription: {transcription}")
        logging.info(f"Transcription: {transcription}")
        type_text_in_active_window(transcription)
    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}")
        print(f"An error occurred during transcription: {e}")


def _signal_handler(signum, frame):
    global _shutdown_requested
    print(f"\n⏹️  Received signal {signum}, shutting down...")
    _shutdown_requested = True

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Desktop Transcription Tool (Offline) - Spracherkennung mit OpenAI Whisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Bedienung:
  Alt+Alt          Aufnahme starten
  Alt+Alt          Aufnahme stoppen + Rest transkribieren
  (automatisch)    Stoppt bei Sprechpause > RECORD_SILENCE_STOP s
  Ctrl+C           Programm beenden

Transkription (Standard: klassisch):
  Die Aufnahme wird beim Stoppen komplett am Stück transkribiert und getippt.
  OFFLINE_LIVE=1 → Live-Modus: Phrasen werden schon während der Aufnahme an
  Sprechpausen transkribiert und sofort am Cursor getippt.

Umgebungsvariablen:
  AUDIO_DEVICE          Input-Device Index (überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Device Index (überschreibt Auswahl)
  WHISPER_MODEL         Modell (tiny/base/small/medium/large, Standard: small)
  OFFLINE_LIVE          0 = alles am Ende (Standard), 1 = live während Aufnahme
  RECORD_SILENCE_STOP   Sprechpause in s bis Auto-Stop, 0 = aus (Standard: 15.0)
  STREAM_SILENCE_RMS    Schwelle Stille-Erkennung (Standard: 0.010)
  STREAM_MIN_SILENCE    Pausenlänge in s zum Phrasen-Ende (Standard: 0.7)
  STREAM_MIN_PHRASE     Minimale Phrasenlänge in s (Standard: 0.4)
  STREAM_MAX_PHRASE     Max. Phrasenlänge in s ohne Pause (Standard: 15.0)

Beispiele:
  ./run_offline.sh                     Interaktive Geräteauswahl (Standard)
  ./run_offline.sh -d                  Schnellstart mit Default-Geräten
  ./run_offline.sh -a                  Ein Gerät für Input + Output
  AUDIO_DEVICE=7 ./run_offline.sh -d   Jabra als Input, Default-Output
        """
    )
    parser.add_argument('-d', '--default', action='store_true',
                        help='Schnellstart: Default-Geräte ohne Auswahl-Menü (Device 0 + 19)')
    parser.add_argument('-a', '--auto', action='store_true',
                        help='Ein Gerät für Input UND Output auswählen (z.B. Jabra Headset)')
    args = parser.parse_args()

    # Nur EINE Transcription-Instanz darf laufen (sonst doppeltes Tippen).
    import _singleinstance
    _singleinstance.acquire_or_exit()

    # Tipp-Backend ermitteln (ydotool/wtype/Clipboard) + ydotoold ggf. starten.
    print(f"⌨️  Tipp-Backend: {_typer.detect_typer()} (Layout: {_typer.KB_LAYOUT})")

    # Interactive mode is TRUE by default, only FALSE if -d is passed
    interactive = not args.default
    auto_device = args.auto

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

    # Device selection
    try:
        if auto_device:
            # Auto mode: select ONE device for input + output
            select_auto_device(interactive=interactive)
        else:
            # Normal mode: select input and output separately
            select_audio_device(interactive=interactive)
            # Output device selection (for beeps)
            try:
                select_output_device(interactive=interactive)
            except Exception as e:
                print(f"Error selecting output device: {e}")
                # Continue without output device (beeps will use default)
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        exit(1)

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
    print(f"   Sample Rate: {samplerate} Hz mono")
    live_txt = "AN (Phrasen während der Aufnahme)" if _live_mode else "AUS (alles am Ende)"
    print(f"   Live-Transkription: {live_txt}")
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