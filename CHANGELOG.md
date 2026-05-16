# Changelog

Alle wichtigen Änderungen werden in dieser Datei dokumentiert.

## [1.3.0] - 2026-05-16

### Added
- Neuer Modus `-a`/`--auto`: Ein Gerät für Input + Output auswählen
  - Praktisch für Headsets mit Mikrofon (z.B. Jabra SPEAK 510)
  - Zeigt nur Geräte mit Input + Output Kanälen
- Verbesserter `--help` Output mit vollständiger Dokumentation
  - Tastenkürzel (Alt+Alt, Ctrl+C)
  - Alle Umgebungsvariablen erklärt
  - Konkrete Beispiele mit Kommandos
- Täglicher Trivy Security Scan (cron, 2:00 Uhr)
  - Scannt `/home/aroc/projects` auf Vulnerabilities
  - Reports in `~/.transcription/trivy-reports/`
  - Automatische Bereinigung nach 7 Tagen

### Changed
- Start-Verhalten umgekehrt:
  - `./run_offline.sh` → Interaktive Geräteauswahl (war: kein Menü)
  - `./run_offline.sh -d` → Schnellstart mit Defaults (ersetzt altes Default-Verhalten)
  - `./run_offline.sh -a` → Ein Gerät für Input + Output
- Argumente werden jetzt korrekt durch Wrapper-Scripts weitergegeben (`"$@"`)

### Fixed
- `-H` Flag funktioniert jetzt in `run_offline.sh` und `offline/run.sh`
- Argumente wurden nicht an Python-Script weitergegeben (fehlende `"$@"`)

## [1.2.1] - 2026-05-12

### Fixed
- User-Service: Clipboard-Zugriff repariert
  - `DISPLAY=:0` und `XAUTHORITY` hinzugefügt, damit xclip funktioniert
  - Vorher: Transkription funktionierte, aber Text ging nicht in Zwischenablage
  - Jetzt: Service und run_offline.sh arbeiten identisch

## [1.2.0] - 2026-05-09

### Added
- User-Service statt System-Service: `~/.config/systemd/user/transcription-offline.service`
  - Läuft als normaler User → PipeWire/Audio funktioniert nativ
  - Kein `DISPLAY`/`XAUTHORITY`-Workaround mehr nötig
  - Verwalten ohne sudo: `systemctl --user start/stop/status transcription-offline.service`
- `run_offline.sh` im Projektroot für bequemen Start ohne Verzeichniswechsel
- Interaktive Geräte-Auswahl mit `-H` Flag
  - `./run.sh` → nutzt Default-Devices automatisch (schnell)
  - `./run.sh -H` → zeigt Geräte-Auswahl-Menü
  - Umgebungsvariablen (`AUDIO_DEVICE`, `AUDIO_OUTPUT_DEVICE`) haben immer Vorrang

### Changed
- `run.sh` und `run_offline.sh` starten jetzt ohne `sudo`
- Voraussetzung: User muss in der Gruppe `input` sein (einmalige Einrichtung)

### Setup (einmalig)
```bash
sudo usermod -aG input $USER
# Ausloggen und wieder einloggen, damit Gruppe aktiv wird
systemctl --user daemon-reload
systemctl --user enable --now transcription-offline.service
```

### System-Service vs. User-Service

| | System-Service | User-Service |
|---|---|---|
| Läuft als | root | $USER |
| Startet | beim Booten | beim Login |
| Audio | braucht Env-Variablen-Hacks | funktioniert direkt |
| Verwalten | `sudo systemctl` | `systemctl --user` |

## [1.1.0] - 2026-04-30

### Added
- 🔊 Audio-Feedback-Sounds für Aufnahmestart und -stopp
  - 800Hz Beep beim Aufnahmestart
  - 1200Hz Beep wenn Aufnahme endet und Text in Zwischenablage kopiert ist
- Flexible Paketversionen in requirements.txt für bessere Kompatibilität

### Fixed
- 🐛 Installation: PEP 668 Kompatibilität (--break-system-packages Flag hinzugefügt)
- 🐛 Hardcodierter Pfad `/home/aroc/PycharmProjects` entfernt
- 🐛 run.sh nutzt jetzt korrekte venv-Pfade mit sudo -E
- 🐛 offline/install.sh versucht nicht mehr, non-existent `transcription_online.py` zu löschen
- 🐛 Ungültige Paketversion `whisper==20240930` in `openai-whisper>=1.0` geändert

## [1.0.0] - 2026-04-28

### Added
- ✅ Master Installer - globale Installation funktioniert jetzt
- ✅ Offline Transkription mit OpenAI Whisper
- ✅ Online Transkription mit Google Speech API
- ✅ Tastatur-Hotkeys (Alt Tap Tap zum Start/Stop)
- ✅ Audio-Aufnahme mit sounddevice
- ✅ Text-zu-Zwischenablage Kopieren (xclip/xsel)
- ✅ Logging in Datei und Konsole
- ✅ CUDA GPU-Unterstützung für Whisper
- ✅ Separate Tools in verschiedenen Verzeichnissen

### Features
- **Offline-Modus**: Funktioniert ohne Internet, verwendet lokales Whisper-Modell
- **Online-Modus**: Nutzt Google Cloud Speech API für höhere Genauigkeit
- **Multi-Gerät**: Auswahl aus verfügbaren Mikrofonen beim Start
- **Automatische Zwischenablage**: Transkribierter Text wird sofort in Zwischenablage kopiert
- **Detailliertes Logging**: Alle Aktionen werden protokolliert

### Technical
- Python 3.12+
- PyTorch 2.x mit CUDA 13 Unterstützung
- sounddevice/soundfile für Audio
- evdev für Tastaturüberwachung
- OpenAI Whisper für Spracherkennung
