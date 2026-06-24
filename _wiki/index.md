# Projekt-Wiki — Desktop Transcription Tool

_Zuletzt aktualisiert: 2026-06-24_

## Inhalt
- [troubleshooting.md](troubleshooting.md) — bekannte Probleme, Diagnose, Fix

## Kurzüberblick
Aufnahme → Whisper-Transkription → Text wird an der Cursor-Position getippt,
ausgelöst per Alt+Alt-Doppeltipp (Wayland/GNOME). Drei Modi:
- `run_offline.sh` — klassisch: aufnehmen → stoppen → Ctrl+V (Clipboard)
- `run_streaming.sh` — VAD-Streaming, Text an Sprechpausen (openai-whisper)
- `run_faster_streaming.sh` — wortweises Live-Streaming (faster-whisper +
  LocalAgreement-2)
