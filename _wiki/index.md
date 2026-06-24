# Projekt-Wiki — Desktop Transcription Tool

_Zuletzt aktualisiert: 2026-06-24_

## Inhalt
- [service.md](service.md) — Service-Setup & Autostart bei Rechnerstart
- [speaker-to-claude.md](speaker-to-claude.md) — Sprich mit Claude Code (claude-Modus)
- [troubleshooting.md](troubleshooting.md) — bekannte Probleme, Diagnose, Fix

## Kurzüberblick
Aufnahme → Whisper-Transkription → Text wird an der Cursor-Position getippt,
ausgelöst per Alt+Alt-Doppeltipp (Wayland/GNOME). Vier Modi:
- `run_offline.sh` — klassisch: aufnehmen → stoppen → Ctrl+V (Clipboard)
- `run_streaming.sh` — VAD-Streaming, Text an Sprechpausen (openai-whisper)
- `run_faster_streaming.sh` — wortweises Live-Streaming (faster-whisper +
  LocalAgreement-2)
- `run_claude.sh` — Sprache → Claude Code (`claude -p`) → Antwort im Fenster
  (Gesprächskontext per fester Session; siehe [speaker-to-claude.md](speaker-to-claude.md))
