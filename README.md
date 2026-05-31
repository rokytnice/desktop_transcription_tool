# Desktop Transcription Tool 🎤

Offline-Spracherkennung mit OpenAI Whisper — aufnehmen, transkribieren, in Zwischenablage kopieren.

## 📁 Projektstruktur

```
desktop_transcription_tool/
├── offline/                      Offline Transkription (Whisper)
│   ├── transcription_offline.py
│   ├── install.sh
│   ├── run.sh
│   ├── requirements.txt
│   └── README.md
│
├── text_improvement/             Text-Verbesserung mit LLM
│   └── transcription_listener_offline_text_improvement.py
│
├── big_audio_file_transcription/ Große Audio-Dateien transkribieren
│   ├── transcribe_audio.py
│   └── requirements.txt
│
├── transcription-offline.service systemd User-Service
├── install.sh                    Installations-Script
├── enable-service.sh             Service einmalig aktivieren
├── restart-service.sh            Service neu starten
└── run_offline.sh                Manuell starten
```

## 🚀 Installation (einmalig)

```bash
# 1. User zur input-Gruppe hinzufügen (Tastaturzugriff ohne sudo)
sudo usermod -aG input $USER
# Ausloggen und wieder einloggen

# 2. Alles installieren (Pakete, venv, Service, globale Kommandos)
./install.sh
```

## ▶️ Starten

```bash
# Als Service (autostart bei Login) — empfohlen
./enable-service.sh

# Manuell
./run_offline.sh          # Interaktive Geräteauswahl
./run_offline.sh -a       # Ein Gerät für Input + Output (z.B. Jabra Headset)
./run_offline.sh -d       # Schnellstart mit Default-Geräten
```

## 🎤 Bedienung

1. **Alt Tap Tap** → Aufnahme startet
2. **Sprechen**
3. **Alt Tap Tap** → Aufnahme stoppt, Whisper transkribiert
4. **Ctrl+V** → Text einfügen

## 🔧 Service-Verwaltung

Nach `./install.sh` sind diese Kommandos überall verfügbar:

```bash
transcription-restart    # Service neu starten
transcription-start      # Service starten
transcription-stop       # Service stoppen
transcription-status     # Status anzeigen
```

Oder direkt mit systemctl:
```bash
systemctl --user status transcription-offline.service
systemctl --user restart transcription-offline.service
journalctl --user -u transcription-offline.service -f   # Live-Log
```

## 🖥️ System-Anforderungen

- Linux mit Wayland (getestet auf Ubuntu 24.04)
- Python 3.12+
- `wl-clipboard` (Wayland Clipboard)
- Mikrofon + Lautsprecher
- Gruppe `input` für Tastaturzugriff ohne sudo

## 📝 Logs

```bash
tail -f ~/.transcription/transcription_listener.log
```
