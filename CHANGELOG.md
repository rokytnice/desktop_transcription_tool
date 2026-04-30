# Changelog

Alle wichtigen Änderungen werden in dieser Datei dokumentiert.

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
