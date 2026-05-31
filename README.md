# Desktop Transcription Tool 🎤

Offline-Spracherkennung mit OpenAI Whisper — aufnehmen, transkribieren, in Zwischenablage kopieren.

## 📁 Projektstruktur

```
desktop_transcription_tool/
├── offline/                      Offline Transkription (Whisper)
│   ├── transcription_offline.py  Hauptprogramm
│   ├── install.sh                Offline-spezifische Installation
│   ├── run.sh                    Direkt starten (ohne Auto-Restart)
│   ├── requirements.txt
│   └── README.md
│
├── text_improvement/             Text-Verbesserung mit LLM (Gemini)
│   └── transcription_listener_offline_text_improvement.py
│
├── big_audio_file_transcription/ Große Audio-Dateien transkribieren
│   ├── transcribe_audio.py
│   └── requirements.txt
│
├── transcription-offline.service systemd User-Service Definition
├── install.sh                    Vollständige Installation
├── enable-service.sh             Service einmalig aktivieren
├── restart-service.sh            Service neu starten
└── run_offline.sh                Manuell starten (mit Auto-Restart)
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
- System-Pakete (`wl-clipboard`, Python 3.12, Audio-Libs)
- Python venv + alle Abhängigkeiten
- systemd User-Service installieren und aktivieren
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

## ⚙️ enable-service.sh

Installiert und aktiviert den systemd User-Service (Autostart bei Login).

```
VERWENDUNG
  ./enable-service.sh [OPTIONEN]

OPTIONEN
  -h, --help   Diese Hilfe anzeigen

BESCHREIBUNG
  Kopiert transcription-offline.service nach ~/.config/systemd/user/,
  aktiviert den Service (Autostart bei Login) und startet ihn sofort.
```

---

## 🔄 restart-service.sh

Startet den laufenden Service neu.

```
VERWENDUNG
  ./restart-service.sh [OPTIONEN]

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

Oder direkt mit systemctl:
```bash
systemctl --user status transcription-offline.service
systemctl --user restart transcription-offline.service
systemctl --user stop transcription-offline.service
journalctl --user -u transcription-offline.service -f    # Live-Log
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

- Linux mit **Wayland** (getestet auf Ubuntu 24.04)
- Python 3.12+
- `wl-clipboard` — Wayland Clipboard (`sudo apt install wl-clipboard`)
- Mikrofon + Lautsprecher
- Gruppe `input` für Tastaturzugriff ohne sudo

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
journalctl --user -u transcription-offline.service -f

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
