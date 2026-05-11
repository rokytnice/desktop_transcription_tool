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

```bash
./run.sh                  # Default: nutzt Standard-Geräte
./run.sh -H              # Interaktiv: Geräte-Auswahl-Menü
```

## Bedienung

1. **Alt Tap Tap** → Recording startet 🔴
2. **Sprechen Sie 2-3 Sekunden** 🗣️
3. **Alt Tap Tap** → Recording stoppt & transkribiert ⏹️
4. **Ctrl+C** → Programm beenden

Text wird automatisch in die Zwischenablage kopiert → **Ctrl+V** zum Einfügen!

## System-Anforderungen

- Python 3.12+
- xclip (für Clipboard)
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
sudo apt install xclip xsel
```
