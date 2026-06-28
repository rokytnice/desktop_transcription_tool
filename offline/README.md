# Offline Transcription Tool 🎤

Lokale Spracherkennung mit OpenAI Whisper - **keine API Key erforderlich!**

## Features

- 🎙️ **Echtzeit-Aufnahme** vom Mikrofon
- 🤖 **Whisper Modell** (lokal, offline)
- 🇩🇪 **Deutsch Support** (auto-detected)
- 📋 **Clipboard-Kopie** (Ctrl+V zum Einfügen)
- ⚡ **Schnell & Zuverlässig**

## Installation

```bash
./install.sh
```

## Start

Gestartet wird über die Wrapper im Projekt-Root (mit Auto-Restart):

```bash
../run_offline.sh         # interaktive Geräteauswahl
../run_offline.sh -a      # ein Gerät für Input + Output (z.B. Jabra)
../run_offline.sh -d      # Schnellstart mit Default-Geräten
```

## Bedienung

1. **Alt Tap Tap** → Recording startet 🔴
2. **Sprechen Sie 2-3 Sekunden** 🗣️
3. **Alt Tap Tap** → Recording stoppt & transkribiert ⏹️
4. **Ctrl+C** → Programm beenden

Der Text wird direkt an der Cursor-Position getippt (gemeinsames Tipp-Backend
`_typer.py`; die Zwischenablage ist nur Fallback, wenn kein Tipp-Tool da ist).

## System-Anforderungen

- Python 3.12+
- wl-clipboard (für Clipboard, Wayland)
- Audio-Geräte (Mikrofon + Lautsprecher)
- ~2GB RAM für Whisper-Modell

## Log

Logs werden gespeichert in: `transcription_listener.log`

## Troubleshooting

**Keine Aufnahme?**
```bash
aplay -L  # Zeige verfügbare Audio-Geräte
```

**Kein Clipboard?**
```bash
sudo apt install wl-clipboard
```
