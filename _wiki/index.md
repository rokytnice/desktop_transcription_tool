# Projekt-Wiki — Desktop Transcription Tool

_Zuletzt aktualisiert: 2026-07-06_

## Inhalt
- [service.md](service.md) — Service-Setup & Autostart bei Rechnerstart
- [speaker-to-claude.md](speaker-to-claude.md) — Sprich mit Claude Code (claude-Modus)
- [duplex-to-claude.md](duplex-to-claude.md) — Mikro + Speaker dauerhaft → Claude (duplex-Modus)
- [troubleshooting.md](troubleshooting.md) — bekannte Probleme, Diagnose, Fix

## Kurzüberblick
Aufnahme → Whisper-Transkription → Text wird an der Cursor-Position getippt,
ausgelöst per Alt+Alt-Doppeltipp (Wayland/GNOME). Fünf Modi:
- `run_offline.sh` — klassisch: aufnehmen → stoppen → Text wird direkt am Cursor
  getippt (gemeinsames Tipp-Backend `_typer.py`; Clipboard nur als Fallback)
- `run_streaming.sh` — VAD-Streaming, Text an Sprechpausen (openai-whisper).
  **Leerlauf-Timeout:** stoppt sich nach `STREAM_IDLE_TIMEOUT` s ohne Sprache
  selbst (Standard 10 s, `0` = aus). Der Auto-Stop läuft in einem eigenen Thread,
  weil `stop()` den Worker joint — ein Aufruf aus dem Worker heraus wäre ein
  Selbst-Join-Deadlock; `start`/`stop` sind per `_lifecycle_lock` serialisiert.
- `run_faster_streaming.sh` — wortweises Live-Streaming (faster-whisper +
  LocalAgreement-2)
- `run_claude.sh` — Sprache → Claude Code (`claude -p`) → Antwort im Fenster
  (Gesprächskontext per fester Session; siehe [speaker-to-claude.md](speaker-to-claude.md))
- `run_duplex_claude.sh` — Mikro **+** Lautsprecher-Monitor dauerhaft mithören
  (via `parec`), an Sprechpausen → Claude → Fenster; kein Alt+Alt, kein Cursor-Tippen
  (siehe [duplex-to-claude.md](duplex-to-claude.md))
