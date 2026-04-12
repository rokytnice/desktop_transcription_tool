# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Desktop Transcription Tool** — A Linux desktop application that captures voice input via keyboard hotkey (Ctrl+Alt), transcribes it locally using OpenAI Whisper, and automatically types the result into the active window.

The tool runs as a background listener that monitors keyboard input at the system level and performs real-time speech-to-text conversion.

## Architecture

### Core Components

- **`transcription_offline.py`** (primary entry point)
  - Local transcription using OpenAI Whisper model
  - Keyboard monitoring via `evdev` (low-level keyboard events)
  - Audio capture using `sounddevice` with auto-sampled rates
  - Text output to active window via `xdotool`
  - Comprehensive logging to `transcription_listener.log`

- **`transcription_online.py`**
  - Google Cloud Speech-to-Text API variant
  - Uses `pynput` for keyboard input (higher-level than evdev)
  - Same audio capture and output logic

- **`transcription_listener_offline_text_improvement.py`**
  - Offline transcription with post-processing
  - Integrates Gemini API for text improvement
  - Same core recording/playback as offline variant

### Key Libraries & Dependencies

**Audio Processing:**
- `sounddevice` — low-latency audio I/O
- `soundfile` — WAV file I/O
- `numpy` — audio array manipulation
- `wave` — WAV format control (sample rate, channels, bit depth)

**Speech Recognition:**
- `openai-whisper` — local model-based transcription (base model, German language)
- `torch` — Whisper dependency; models are quantized to int8 for memory efficiency

**Input/Output:**
- `evdev` — raw keyboard event monitoring (replaces older pynput usage in offline variant)
- `xdotool` — type text into active window, handles non-ASCII chars via Unicode codes

**External APIs (optional):**
- `google-generativeai` — Gemini API for text improvement
- `requests` — HTTP for Google Cloud Speech

**Logging:**
- Python standard `logging` module — dual output (console + file)

## Development Setup

### System Requirements

- Linux with X11/X server (GUI required)
- Python 3.10+
- System packages: `ffmpeg`, `xdotool`
- User must be logged into desktop session (for X server access)

### First Run — Install Dependencies

```bash
# Navigate to project root
cd /path/to/desktop_transcription_tool_

# Run the dependency installer (requires sudo for system packages)
bash install_deps.sh
```

This script:
1. Updates package manager (`apt update`)
2. Installs `ffmpeg` and `xdotool`
3. Creates Python virtual environment (`.venv`)
4. Installs PyTorch with CUDA 11.8 support
5. Installs Python dependencies from `requirements.txt`

### Running the Application

**Recommended — Use the launcher script:**

```bash
# Auto-checks for venv, installs if missing, then runs the tool
bash wispr.sh
```

Or:

```bash
# Checks permissions, then runs
bash install_transscription_offline.sh
```

**Direct execution (if already set up):**

```bash
source .venv/bin/activate
python3 transcription_offline.py
```

## Usage

1. Start the script (it will monitor keyboard input)
2. **Hold Ctrl+Alt** to start recording
3. **Release Ctrl+Alt** to stop recording and transcribe
4. Transcribed text automatically types into the active window

Logs are written to `transcription_listener.log`.

## Configuration

### Environment Variables

- `GEMINI_LLM` — Model name for Gemini API (used in text improvement script)
  - Default: `gemini-2.5-flash-lite-preview-06-17`
- `DISPLAY` — Required to connect to X server (usually set automatically)
- `LC_ALL`, `LANG` — Hardcoded to `de_DE.UTF-8` (German locale)

### Key Settings (Hardcoded)

- **Transcription Language:** German (`"de"`)
- **Whisper Model Size:** `"base"` (balances speed/accuracy)
- **Audio Sample Rates:** Auto-detected from device, tried in order: 16000, 22050, 44100, 48000 Hz
- **Whisper Quantization:** int8 (reduces memory overhead)
- **Keyboard Hotkey:** Left/Right Ctrl + Left/Right Alt (any combination)

To change language or model size, edit `transcription_offline.py:135`:
```python
result = model.transcribe(audio_file_path, fp16=True, language="de", task="transcribe")
```

## Common Development Tasks

### Running the Primary Script

```bash
source .venv/bin/activate
python3 transcription_offline.py
```

### Installing/Updating Dependencies

```bash
source .venv/bin/activate
pip install -r requirements.txt

# For CUDA-enabled PyTorch:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Checking Logs

```bash
# Real-time log monitoring
tail -f transcription_listener.log

# View all logs
cat transcription_listener.log
```

### Debugging Keyboard Input

If the hotkey isn't detected:
1. Check `transcription_listener.log` for device detection errors
2. Verify keyboard device is accessible: `ls /dev/input/event*`
3. Confirm user is logged into desktop (not SSH)

### Testing Audio Capture Independently

```python
import sounddevice as sd
import soundfile as sf

# Record 5 seconds at 16kHz
duration = 5
fs = 16000
audio = sd.rec(int(fs * duration), samplerate=fs, channels=1, dtype='int16')
sd.wait()
sf.write('test.wav', audio, fs)
```

### Checking X Server Permissions

```bash
# Verify X server access
xset q

# Grant X server access if needed
xhost +SI:localuser:$USER
```

## Architecture Notes

### Audio Pipeline

1. **Hotkey Detection** → evdev monitors `/dev/input/event*` for Ctrl+Alt
2. **Recording** → sounddevice callback accumulates audio frames into `audio_data` list
3. **Saving** → numpy concatenates frames, wave module writes as int16 WAV
4. **Transcription** → Whisper loads cached model, quantizes to int8, transcribes WAV
5. **Output** → xdotool types each character, using Unicode for non-ASCII

### Logging Strategy

Dual output (console + file) using standard Python logging:
- Console: debug level, human-readable format
- File (`transcription_listener.log`): appends with timestamps

### Device/Permission Model

- Requires direct `/dev/input` access for evdev keyboard monitoring
- Requires X11 connection for xdotool and window focus
- Must run as logged-in desktop user (not root, not SSH)

## Important Constraints & Gotchas

1. **Locale is German** — Hardcoded to `de_DE.UTF-8`; change if supporting other languages
2. **X Server required** — Only works in graphical desktop sessions, not SSH/headless
3. **Device-specific sample rates** — Auto-detection tries standard rates; may need manual tuning for unusual hardware
4. **Whisper model caching** — First run downloads ~140 MB (base model); subsequent runs use cache
5. **evdev requires device permissions** — May need to run as user in `input` group or use `run_sudo.sh`
6. **Non-ASCII typing** — Uses xdotool's Unicode input method, slower than ASCII

## Related Documentation

- `functional_requirements.md` — User-facing requirements (in German)
- `design_talk_analyser.md` — Design notes on text improvement features
- `transcription_listener_offline_text_improvement.md` — (empty placeholder)
