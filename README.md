# Desktop Transcription Tool 🎤

Offline-Spracherkennung mit Whisper. Drei Modi:

- **Klassisch** (`run_offline.sh`) — aufnehmen → stoppen → Text in Zwischenablage (Ctrl+V).
- **Streaming an Sprechpausen** (`run_streaming.sh`) — VAD-basiert: tippt die erkannte
  Phrase **an jeder Sprechpause** live an der Cursor-Position. Kein Warten, kein Ctrl+V.
- **Wortweises Live-Streaming** (`run_faster_streaming.sh`) — faster-whisper +
  LocalAgreement: tippt Text **wortweise WÄHREND des Sprechens**, auch mitten im Satz.

## 📁 Projektstruktur

```
desktop_transcription_tool/
├── offline/                       Offline Transkription (Whisper)
│   ├── transcription_offline.py   Klassisch: aufnehmen → stoppen → einfügen
│   ├── transcription_streaming.py Streaming an Sprechpausen (VAD)
│   ├── transcription_faster_streaming.py  Wortweises Live-Streaming (faster-whisper)
│   ├── install.sh                 Offline-spezifische Installation
│   ├── run.sh                     Direkt starten (ohne Auto-Restart)
│   ├── requirements.txt
│   └── README.md
│
├── text_improvement/              Text-Verbesserung mit LLM (Gemini)
│   └── transcription_listener_offline_text_improvement.py
│
├── big_audio_file_transcription/  Große Audio-Dateien transkribieren
│   ├── transcribe_audio.py
│   └── requirements.txt
│
├── install.sh                     Vollständige Installation
├── setup-service.sh               Service einrichten (Autostart bei Boot)
├── enable-service.sh              Wrapper auf setup-service.sh
├── restart-transcription-service.sh  Service neu starten
├── run_offline.sh                 Klassisch starten (mit Auto-Restart)
├── run_streaming.sh               Streaming an Sprechpausen (mit Auto-Restart)
└── run_faster_streaming.sh        Wortweises Live-Streaming (mit Auto-Restart)
```

---

## 🚀 Installation (einmalig)

```bash
# 1. User zur input-Gruppe hinzufügen (Tastaturzugriff ohne sudo)
sudo usermod -aG input $USER
# Ausloggen und wieder einloggen damit die Gruppe aktiv wird

# 2. Alles installieren
./install.sh
```

`install.sh` erledigt automatisch:
- System-Pakete (`wl-clipboard`, `ydotool`, `wtype`, Python 3.12, Audio-Libs)
- Python venv + alle Abhängigkeiten
- systemd User-Service einrichten (Autostart bei Rechnerstart, via `setup-service.sh`)
- Globale Kommandos nach `~/.local/bin/` installieren

---

## ▶️ run_offline.sh

Startet das Tool manuell mit automatischem Neustart bei Absturz.

```
VERWENDUNG
  ./run_offline.sh [OPTIONEN]

OPTIONEN
  (kein Flag)   Interaktive Geräteauswahl beim Start
  -a, --auto    Ein Gerät für Input UND Output (z.B. Jabra Headset)
  -d, --default Schnellstart mit System-Default-Geräten, kein Menü
  -h, --help    Diese Hilfe anzeigen

UMGEBUNGSVARIABLEN
  AUDIO_DEVICE          Input-Gerät (Index, überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Gerät (Index, überschreibt Auswahl)
  WHISPER_MODEL         tiny|base|small|medium|large  (Standard: small)

BEISPIELE
  ./run_offline.sh                      Interaktive Geräteauswahl
  ./run_offline.sh -a                   Jabra-Modus: ein Gerät für alles
  ./run_offline.sh -d                   Schnellstart, kein Menü
  AUDIO_DEVICE=7 ./run_offline.sh -d    Gerät 7 als Input, Default-Output
  WHISPER_MODEL=medium ./run_offline.sh Größeres Modell verwenden
```

---

## ⚡ run_streaming.sh (Echtzeit-Streaming)

Transkribiert **kontinuierlich während des Sprechens** und tippt den erkannten Text
**live an der Cursor-Position** — kein Stoppen, kein Ctrl+V. Eine Voice-Activity-Detection
schneidet an natürlichen Sprechpausen, sodass keine Wörter mitten im Wort getrennt werden.

```
VERWENDUNG
  ./run_streaming.sh [OPTIONEN]

OPTIONEN
  (kein Flag)   Interaktive Geräteauswahl beim Start
  -a, --auto    Ein Gerät für Input UND Output (z.B. Jabra Headset)
  -d, --default Schnellstart mit System-Default-Geräten, kein Menü
  -h, --help    Diese Hilfe anzeigen

UMGEBUNGSVARIABLEN
  AUDIO_DEVICE          Input-Gerät (Index, überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Gerät (Index, für Beeps)
  WHISPER_MODEL         tiny|base|small|medium|large  (Standard: small)
  STREAM_SILENCE_RMS    Schwelle Stille-Erkennung                 (Standard: 0.010)
  STREAM_MIN_SILENCE    Pausenlänge in s bis Phrase getippt wird  (Standard: 0.7)
  STREAM_MIN_PHRASE     Minimale Phrasenlänge in s                (Standard: 0.4)
  STREAM_MAX_PHRASE     Max. Phrasenlänge in s ohne Pause         (Standard: 15.0)

BEISPIELE
  ./run_streaming.sh                      Interaktive Geräteauswahl
  ./run_streaming.sh -a                   Jabra-Modus: ein Gerät für alles
  WHISPER_MODEL=tiny ./run_streaming.sh   Schnellstes Modell, geringste Latenz
```

**Bedienung:** Alt+Alt startet/stoppt das Streaming, dann einfach sprechen — der Text
erscheint an jeder Sprechpause direkt im fokussierten Fenster.

### Live-Tippen am Cursor — Backends

Das Streaming wählt das Tipp-Backend automatisch:

| Backend | Bedingung | Verhalten |
|---|---|---|
| `ydotool` | GNOME/Mutter & jeder Wayland-Compositor | Kernel-uinput, tippt direkt ✅ |
| `wtype` | wlroots (Sway, Hyprland) | virtual-keyboard-Protokoll |
| Zwischenablage | wenn keins der beiden nutzbar | `wl-copy`, manuell Ctrl+V |

`ydotool` benötigt einen laufenden `ydotoold`-Daemon und Zugriff auf `/dev/uinput`
(Gruppe `input`). Das Tool startet `ydotoold` bei Bedarf automatisch im User-Kontext.

> **GNOME-Hinweis:** `wtype` funktioniert auf GNOME **nicht** (Mutter unterstützt das
> virtual-keyboard-Protokoll nicht). Deshalb wird dort `ydotool` verwendet.

---

## ⚡⚡ run_faster_streaming.sh (Wortweises Live-Streaming)

Die schnellste Variante: tippt Text **wortweise WÄHREND des Sprechens** — auch mitten
im Satz, nicht erst an der Sprechpause. Technik:

- **faster-whisper** (CTranslate2) statt openai-whisper — 3-4× schneller, weniger RAM
  (`int8` auf CPU, `float16` auf GPU).
- **LocalAgreement-2** (Macháček et al., *whisper_streaming*): ein wachsender Audio-Puffer
  wird ~jede Sekunde neu transkribiert; nur Wörter, die über **zwei aufeinanderfolgende
  Läufe stabil** bleiben, werden festgeschrieben und sofort getippt. Das verhindert
  flackernde, ständig korrigierte Ausgabe bei niedriger Latenz.

```
VERWENDUNG
  ./run_faster_streaming.sh [OPTIONEN]

OPTIONEN
  (kein Flag)   Interaktive Geräteauswahl beim Start
  -a, --auto    Ein Gerät für Input UND Output (z.B. Jabra Headset)
  -d, --default Schnellstart mit System-Default-Geräten, kein Menü
  -h, --help    Diese Hilfe anzeigen

UMGEBUNGSVARIABLEN
  AUDIO_DEVICE          Input-Gerät (Index, überschreibt Auswahl)
  AUDIO_OUTPUT_DEVICE   Output-Gerät (Index, für Beeps)
  WHISPER_MODEL         tiny|base|small|medium|large  (Standard: small)
  STREAM_MIN_CHUNK      Update-Takt in s (~2s ≈ 3-5 Wörter pro Schub)  (Standard: 2.0)
  STREAM_MAX_BUFFER     Puffer-Obergrenze in s vor Beschnitt           (Standard: 18.0)
  STREAM_BEAM           Beam-Size (1 = geringste Latenz)               (Standard: 1)

BEISPIELE
  ./run_faster_streaming.sh                      Standard: small, ~3-5 Wörter pro Schub
  ./run_faster_streaming.sh -a                   Jabra-Modus: ein Gerät für alles
  STREAM_MIN_CHUNK=1.0 WHISPER_MODEL=base ./run_faster_streaming.sh   Eher wortweise
```

**Bedienung:** Alt+Alt startet/stoppt das Streaming, dann sprechen — der Text erscheint
in kleinen Schüben (Standard ~3-5 Wörter) im fokussierten Fenster. Tipp-Backends
(ydotool/wtype/Clipboard) wie oben.

> **CPU-Tipp:** Beim Standard-Takt (2 s) hält `small` auch auf reiner CPU Schritt, weil
> das Modell pro Sprechsekunde nur einmal läuft. Möglichst **wortweise** Ausgabe gibt es
> mit kleinerem Takt + kleinerem Modell (`STREAM_MIN_CHUNK=1.0 WHISPER_MODEL=base`); auf
> GPU ist auch das mit `small`/`medium` flüssig. Der Clipboard-Fallback ist für diesen
> Modus ungeeignet (jeder Schub würde den vorigen überschreiben) — also `ydotool`/`wtype`
> sicherstellen.

### Welcher Streaming-Modus?

| | `run_streaming.sh` (VAD) | `run_faster_streaming.sh` (LocalAgreement) |
|---|---|---|
| Engine | openai-whisper | faster-whisper (3-4× schneller) |
| Ausgabe erscheint | an der Sprechpause | wortweise beim Sprechen |
| Latenz | pro Phrase | ~1-2 s pro Wortgruppe |
| Beste Genauigkeit | etwas höher (ganze Phrase) | leicht geringer (inkrementell) |
| CPU-Last | niedriger | höher (wiederholtes Decoden) |

---

## ⚙️ setup-service.sh — Service einrichten (Autostart bei Rechnerstart)

Richtet den Transcription-Service ein und sorgt dafür, dass er **bei jedem
Rechnerstart** automatisch läuft.

```
VERWENDUNG
  ./setup-service.sh [MODUS] [OPTIONEN]

MODUS
  faster-streaming   Wortweises Live-Streaming (faster-whisper)   [Standard]
  streaming          VAD-Streaming an Sprechpausen (openai-whisper)
  offline            Klassisch: aufnehmen → stoppen → Clipboard

OPTIONEN
  --model NAME   Whisper-Modell (tiny|base|small|medium|large)  (Standard: small)
  --device IDX   Audio-Gerät-Index (Input+Output)               (Standard: Auto)
  --no-start     Nur einrichten + aktivieren, nicht sofort starten
  -h, --help     Diese Hilfe anzeigen
```

**Wie der Autostart funktioniert:** Das Skript erzeugt eine modus-spezifische
systemd-User-Unit (`transcription-<modus>.service`) mit automatisch erkannten
Pfaden, aktiviert `loginctl enable-linger` (der User-Manager startet schon bei
Boot) und bindet die Unit an `graphical-session.target` — sie startet also,
sobald die Wayland-Sitzung steht (Tippen an der Cursor-Position braucht eine
aktive Sitzung). Beim Wechsel des Modus werden die anderen Units automatisch
abgeschaltet, sodass immer nur einer läuft. `enable-service.sh` ist ein Wrapper
auf dieses Skript.

```bash
./setup-service.sh                         # faster-streaming, Modell small
./setup-service.sh offline                 # klassischer Offline-Modus
./setup-service.sh faster-streaming --model tiny   # geringste Latenz
```

---

## 🔄 restart-transcription-service.sh

Startet den laufenden Service neu.

```
VERWENDUNG
  ./restart-transcription-service.sh [OPTIONEN]

OPTIONEN
  -h, --help   Diese Hilfe anzeigen
```

---

## 🔧 Globale Service-Kommandos

Nach `./install.sh` sind diese Kommandos **überall** im Terminal verfügbar:

| Kommando | Funktion |
|---|---|
| `transcription-restart` | Service neu starten |
| `transcription-start` | Service starten |
| `transcription-stop` | Service stoppen |
| `transcription-status` | Status + letzte Log-Zeilen |
| `transcription-log` | Live-Log (`journalctl -f`) |

Die globalen Kommandos sind **modus-unabhängig** — sie zeigen automatisch auf
den zuletzt eingerichteten Modus. Direkt mit systemctl (Unit-Name = `transcription-<modus>.service`):
```bash
systemctl --user status transcription-faster-streaming.service
journalctl --user -u transcription-faster-streaming.service -f    # Live-Log
```

---

## 🎤 Bedienung

| Aktion | Tastenkürzel |
|---|---|
| Aufnahme starten | **Alt + Alt** (Doppeltipp) |
| Aufnahme stoppen + transkribieren | **Alt + Alt** (Doppeltipp) |
| Programm beenden | **Ctrl+C** |
| Text einfügen (nach Transkription) | **Ctrl+V** |

---

## 🖥️ System-Anforderungen

- Linux mit **Wayland** (getestet auf Ubuntu 24.04, GNOME)
- Python 3.12+
- `wl-clipboard` — Wayland Clipboard (`sudo apt install wl-clipboard`)
- `ydotool` (+ `wtype`) — Live-Tippen am Cursor im Streaming-Modus
- Mikrofon + Lautsprecher
- Gruppe `input` für Tastaturzugriff (und `ydotool`/`/dev/uinput`) ohne sudo

---

## 🗂️ Whisper-Modelle

| Modell | Größe | Geschwindigkeit | Genauigkeit |
|---|---|---|---|
| tiny | ~75 MB | sehr schnell | geringer |
| base | ~145 MB | schnell | mittel |
| **small** | ~465 MB | mittel | **gut (Standard)** |
| medium | ~1.5 GB | langsam | sehr gut |
| large | ~3 GB | sehr langsam | beste |

Modell wechseln:
```bash
WHISPER_MODEL=medium ./run_offline.sh
```

---

## 📝 Logs

```bash
# Live-Log
journalctl --user -u transcription-faster-streaming.service -f

# Log-Datei
tail -f ~/.transcription/transcription_listener.log
```

---

## ⚠️ Troubleshooting

**Service gestoppt nach langer Aufnahme?**
Der OOM-Killer beendet den Prozess wenn RAM knapp wird (Whisper lädt Audio komplett in den Speicher). Lange Aufnahmen (>2 Minuten) vermeiden oder Modell `tiny`/`base` verwenden.

**Kein Clipboard?**
```bash
sudo apt install wl-clipboard
```

**Streaming tippt nicht am Cursor (nur Zwischenablage)?**
```bash
# ydotool + Daemon installieren
sudo apt install ydotool wtype

# Zugriff auf /dev/uinput sicherstellen (Gruppe input)
groups $USER | grep input || sudo usermod -aG input $USER
# danach aus- und wieder einloggen

# Daemon manuell prüfen/starten (das Tool startet ihn sonst automatisch)
ydotoold --socket-path="$XDG_RUNTIME_DIR/.ydotool_socket" --socket-own="$(id -u):$(id -g)" &
```
Auf GNOME funktioniert `wtype` nicht — dort wird `ydotool` benötigt.

**Kein Audiogerät gefunden?**
```bash
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

**Tastatur wird nicht erkannt?**
```bash
# Prüfen ob User in input-Gruppe ist
groups $USER | grep input

# Falls nicht:
sudo usermod -aG input $USER
# Ausloggen und wieder einloggen
```
