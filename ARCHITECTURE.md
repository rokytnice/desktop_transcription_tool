# Desktop Transcription Tool - Architektur

## 📐 System Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│  Desktop Transcription Tool - Real-time Streaming          │
└─────────────────────────────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────▼────┐   ┌────▼────┐   ┌────▼─────┐
     │ Keyboard │   │  Audio  │   │ Whisper  │
     │ Listener │   │ Capture │   │  Model   │
     └────┬────┘   └────┬────┘   └────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                  ┌──────▼──────┐
                  │   Daemon    │
                  │  (v3.py)    │
                  └──────┬──────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────▼────┐   ┌────▼────┐   ┌────▼─────┐
     │Streaming│   │ydotool  │   │ Systemd  │
     │Transcr. │   │ (Text)  │   │ Service  │
     └────┬────┘   └────┬────┘   └────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                  ┌──────▼──────┐
                  │Active Window│
                  │  (Inject)   │
                  └─────────────┘
```

---

## 🔧 Komponenten

### 1. **Keyboard Listener Thread** (`keyboard_listener()`)
- **Zweck:** Überwacht `/dev/input/event*` auf Alt-Tasten-Doppeltaps
- **Technologie:** `evdev` (Low-Level Linux Input Events)
- **Hotkey:** Alt + Alt (Doppeltap innerhalb 0.5s)
- **Ausgabe:** Signale `start_recording()` oder `stop_recording()`

```python
# Doppeltap-Erkennung
if alt_press within 0.5 seconds:
    toggle_recording()
```

---

### 2. **Audio Recording** (`audio_callback_vad()`)
- **Technologie:** `sounddevice` (I/O) + `numpy` (Verarbeitung)
- **Sample Rate:** 16kHz (optimal für Whisper)
- **Format:** 32-bit float, mono
- **Puffer:** Ringbuffer in `audio_data[]`
- **Callback:** Läuft in realtime beim Recording

```python
while recording:
    audio_data.append(audio_chunk)  # ~20ms chunks
```

---

### 3. **Streaming Transcriber Thread** (`streaming_transcriber()`)
- **Zweck:** Echtzeit-Transkription während Recording läuft
- **Interval:** 0.5 Sekunden
- **Workflow:**
  1. Alle Audio seit Recording-Start nehmen
  2. In WAV schreiben (temp file)
  3. Mit Whisper transcribieren
  4. Mit `find_new_text()` nur neue Worte extrahieren
  5. Mit `ydotool` in aktives Fenster injizieren

```
Recording starts:  [----audio_data buffer----]
At 0.5s:         Transkribie -> "Hallo Welt" -> Inject
At 1.0s:         Transkribie -> "Hallo Welt wie" -> Inject " wie"
At 1.5s:         Transkribie -> "Hallo Welt wie geht" -> Inject " geht"
```

---

### 4. **Whisper Model**
- **Modell:** `tiny` (aktuell für Speed)
- **Backend:** `faster-whisper` (CTranslate2) - 10x schneller als OpenAI Whisper
- **Sprache:** German (de)
- **Quantization:** float32 (auf CPU)
- **Load Time:** ~10-15s beim Start (dann cached)

```python
from faster_whisper import WhisperModel
model = WhisperModel("tiny", device="auto")
segments, _ = model.transcribe("audio.wav", language="de")
```

---

### 5. **Text Deduplication** (`remove_duplicate_phrases()`)
- **Problem:** Whisper halluziniert manchmal und wiederholt Phrasen
- **Lösung:** Entfernt doppelte Sätze (split by ". ")
- **Beispiel:**
  - Input: "Das ist ein Test. Das ist ein Test. Das ist ein Test."
  - Output: "Das ist ein Test."

---

### 6. **Text Injection** (`inject_text()`)
- **Technologie:** `ydotool` (Wayland-kompatibel, nicht xdotool)
- **Method:** Unix Socket → `/run/ydotool/.ydotool_socket`
- **Zweck:** Simulates keyboard input, types text into active window
- **Environment:** Muss `YDOTOOL_SOCKET` setzen

```bash
YDOTOOL_SOCKET=/run/ydotool/.ydotool_socket ydotool type "Text"
```

---

### 7. **Systemd Service**
- **File:** `~/.config/systemd/user/transcribe.service`
- **Type:** `simple`
- **Auto-Start:** Ja (enabled)
- **Logging:** journalctl integration

```ini
[Service]
ExecStart=.../transcribe_daemon_v3.py
Restart=on-failure
RestartSec=5
```

---

## 🔄 Datenfluss

### Startup Sequence

```
1. ./start.sh
   ├─ Prüft input group (newgrp input falls nötig)
   ├─ Startet systemd service (transcribe.service)
   └─ Zeigt live logs (journalctl)

2. systemd startet transcribe_daemon_v3.py
   ├─ Loaded Whisper model (tiny)
   ├─ Started keyboard listener thread
   ├─ Started socket server (für client commands)
   └─ Ready for hotkey input

3. Daemon waits for user input...
```

### Recording Sequence

```
User: Alt-Alt (double-tap)
  ↓
keyboard_listener() detects double-tap
  ↓
start_recording():
  ├─ Set recording = True
  ├─ Launch streaming_transcriber() thread
  ├─ Launch input_stream callback
  ├─ Play beep (800Hz)
  └─ logger: "▶️  Starting recording"
  ↓
User speaks into microphone (10-30 seconds)
  ↓
Audio captured in real-time
  ├─ sounddevice callback fires ~50x per second
  ├─ Each chunk appended to audio_data[]
  └─ ~20ms of audio per chunk
  ↓
Streaming thread (every 0.5s):
  ├─ Takes snapshot of audio_data
  ├─ Transcribes with Whisper
  ├─ Extracts new words (find_new_text)
  ├─ Deduplicates (remove_duplicate_phrases)
  ├─ Injects with ydotool
  └─ Logger: "🔴 STREAMING: new text '...'"
  ↓
User: Alt-Alt again (double-tap)
  ↓
stop_recording():
  ├─ Set recording = False, streaming = False
  ├─ Stop input_stream
  ├─ Wait for streaming thread to finish
  ├─ Play beep (400Hz)
  ├─ Do final transcription of ALL audio
  ├─ Inject any remaining new words
  └─ Logger: "✅ FINAL TEXT: '...'"
  ↓
Text appears in active window!
```

---

## 📊 Performance Profile

| Component | Duration | Bottleneck |
|-----------|----------|-----------|
| Hotkey detection | <1ms | None |
| Audio capture | Real-time | sounddevice |
| Streaming interval | 0.5s | Whisper transcription |
| Whisper inference (tiny) | 1-2s per 0.5s audio | CPU |
| ydotool injection | 100-500ms | Network socket |
| **Total latency** | **~2-3 seconds** | Whisper model |

---

## 🔐 Permissions & Security

### Required Permissions

1. **Input Group (gid 995)**
   - Zugriff auf `/dev/input/event*` für Keyboard
   - Via: `usermod -aG input <user>` oder `newgrp input`

2. **ydotool Socket**
   - Datei: `/run/ydotool/.ydotool_socket`
   - Permissions: 0666 (readable/writable by all)
   - Systemd service: `/etc/systemd/system/ydotoold.service`

3. **X11/Wayland**
   - DISPLAY variable (automatisch gesetzt)
   - Lokale Benutzer-Session erforderlich

---

## 🗂️ File Structure

```
desktop_transcription_tool/
├── transcribe_daemon_v3.py      # Main daemon (400 lines)
├── start.sh                      # Launcher script
├── install.sh                    # Installation script
├── fix_keyboard_access.sh        # udev rule setup
├── requirements.txt              # Python dependencies
├── .bashrc                       # Input group auto-activation
└── .config/systemd/user/
    └── transcribe.service       # systemd service definition
```

---

## 🔌 IPC Methods

### 1. Unix Socket (Client Commands)
- **File:** `~/.cache/transcribe.sock`
- **Protocol:** JSON over TCP
- **Commands:** `start`, `stop`, `status`

```bash
echo "start" | nc -U ~/.cache/transcribe.sock
```

### 2. Signal Handlers
- `SIGTERM`: Graceful shutdown
- `SIGINT`: Graceful shutdown

### 3. journalctl Logging
- **Output:** `journalctl --user -u transcribe -f`
- **Level:** INFO (debug hidden)
- **Format:** ISO timestamps with emojis

---

## 🚀 Optimization Flags

```python
# Modell-Größe (Speed vs Accuracy)
MODEL_NAME = "tiny"      # Fast (aktuell)
# MODEL_NAME = "small"   # Balanced
# MODEL_NAME = "medium"  # Accurate but slow

# Streaming interval
STREAM_INTERVAL = 0.5    # 2 updates pro Sekunde
# Früher: 1.0, 2.0

# Doppeltap timeout
DOUBLE_TAP_TIMEOUT = 0.5 # 500ms window
# Früher: 0.3
```

---

## 💾 Data Flow Diagram

```
Keyboard Event
    ↓
evdev listener
    ↓ (Alt+Alt detected)
    ├─→ start_recording()
    │       ↓
    │   Audio Callback
    │       ↓
    │   audio_data[] buffer
    │       ↓
    │   Streaming Thread (0.5s)
    │       ├─→ Snapshot audio
    │       ├─→ Whisper transcribe
    │       ├─→ Deduplicate
    │       ├─→ Find new text
    │       └─→ ydotool inject
    │
    └─→ stop_recording()
            ↓
        Final transcription
            ↓
        Remaining text
            ↓
        ydotool inject
            ↓
        Active Window
```

---

## 🔄 State Machine

```
     ┌─────────────────────────────────────┐
     │          IDLE / READY               │
     │  (Listening for Alt double-tap)    │
     └────────────────┬────────────────────┘
                      │
                Alt+Alt (1st)
                      │
     ┌────────────────▼────────────────────┐
     │      FIRST_PRESS_REGISTERED         │
     │  (Waiting for 2nd press within 0.5s)│
     └────────────────┬────────────────────┘
                      │
              Alt+Alt (2nd, <500ms)
                      │
     ┌────────────────▼────────────────────┐
     │       RECORDING / STREAMING         │
     │  ├─ Audio capture (real-time)      │
     │  ├─ Streaming thread (every 0.5s) │
     │  ├─ Text injection (live)         │
     │  └─ Beep on start (800Hz)         │
     └────────────────┬────────────────────┘
                      │
              Alt+Alt (2nd tap)
                      │
     ┌────────────────▼────────────────────┐
     │    FINALIZING TRANSCRIPTION        │
     │  ├─ Stop streaming thread          │
     │  ├─ Final transcription            │
     │  ├─ Remaining text injection       │
     │  └─ Beep on stop (400Hz)           │
     └────────────────┬────────────────────┘
                      │
                   BACK TO
                   IDLE
```

---

## 🐛 Known Limitations

1. **CPU-only Inference**
   - Keine GPU → langsamer als mit CUDA
   - Aber: Tiny model ist schnell genug

2. **Whisper Hallucinations**
   - Model wiederholt manchmal Phrasen
   - Gelöst durch: Deduplication

3. **Latency**
   - ~2-3 Sekunden Verzögerung (Whisper inference)
   - Real-time ist relativ: Text erscheint während du sprichst

4. **No Streaming Whisper**
   - Whisper ist nicht designed für echtes Streaming
   - Workaround: Sliding window + deduplication

---

## 🔧 Debugging

### Logs anschauen
```bash
journalctl --user -u transcribe -f
```

### Keyboard Test
```bash
python3 test_keyboard_input.py
```

### Audio Test
```bash
python3 test_full_workflow.py
```

### ydotool Test
```bash
YDOTOOL_SOCKET=/run/ydotool/.ydotool_socket ydotool type "Test"
```

---

## 📝 Zusammenfassung

Das **Desktop Transcription Tool** ist ein echtzeitiges Speech-to-Text-System, das:

1. **Hotkey-basiert** ist (Alt double-tap)
2. **Streaming** nutzt (0.5s Intervalle)
3. **Lokal** funktioniert (Whisper offline)
4. **Wayland-kompatibel** ist (ydotool)
5. **Dedupliziert** (gegen Halluzinationen)
6. **Systemd-integriert** ist (Auto-start)
7. **Text direkt injiziert** (in aktives Fenster)

**Status:** Production Ready ✅
