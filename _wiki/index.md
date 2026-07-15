# Projekt-Wiki — Desktop Transcription Tool

_Zuletzt aktualisiert: 2026-07-15_

## Inhalt
- [service.md](service.md) — Service-Setup & Autostart bei Rechnerstart
- [speaker-to-claude.md](speaker-to-claude.md) — Sprich mit Claude Code (claude-Modus)
- [duplex-to-claude.md](duplex-to-claude.md) — Mikro + Speaker dauerhaft → Claude (duplex-Modus)
- [meeting.md](meeting.md) — Meeting: Transkript + Live-Stichpunkte + Protokoll (meeting-Modus)
- [troubleshooting.md](troubleshooting.md) — bekannte Probleme, Diagnose, Fix

## Kurzüberblick
Aufnahme → Whisper-Transkription → Text wird an der Cursor-Position getippt,
ausgelöst per Alt+Alt-Doppeltipp (Wayland/GNOME). Sechs Modi:
- `run_offline.sh` — Aufnahme + **Live-Pipelining** (Standard): während der
  Aufnahme transkribiert ein Hintergrund-Worker Phrasen an Sprechpausen (VAD)
  und tippt sie sofort am Cursor — kein langes Warten am Ende, beim Stoppen ist
  nur der letzte kurze Rest offen. Die volle Aufnahme wird trotzdem als WAV
  gesichert. Aufnahme fest 16 kHz mono float32 (whisper-nativ). `OFFLINE_LIVE=0`
  → altes Verhalten (aufnehmen → stoppen → alles am Stück). Tipp-Backend
  `_typer.py` (Clipboard nur Fallback). Segment-Tuning teilt sich die
  `STREAM_MIN_SILENCE`/`STREAM_MIN_PHRASE`/`STREAM_MAX_PHRASE`-Schwellen mit dem
  Streaming-Modus.
  **Pausen-Auto-Stop:** Sprechpause > `RECORD_SILENCE_STOP` s (Standard 15, `0` = aus)
  stoppt die Aufnahme und transkribiert — greift auch im claude-Modus (erbt offline).
- `run_streaming.sh` — VAD-Streaming, Text an Sprechpausen (openai-whisper).
  **Leerlauf-Timeout:** stoppt sich nach `STREAM_IDLE_TIMEOUT` s ohne Sprache
  selbst (Standard 15 s, `0` = aus). Der Auto-Stop läuft in einem eigenen Thread,
  weil `stop()` den Worker joint — ein Aufruf aus dem Worker heraus wäre ein
  Selbst-Join-Deadlock; `start`/`stop` sind per `_lifecycle_lock` serialisiert.
- `run_faster_streaming.sh` — wortweises Live-Streaming (faster-whisper +
  LocalAgreement-2). Gleicher 15-s-Leerlauf-Auto-Stop (`STREAM_IDLE_TIMEOUT`),
  ebenfalls über eigenen Thread wegen Worker-Self-Join.
- `run_claude.sh` — Sprache → Claude Code (`claude -p`) → Antwort im Fenster
  (Gesprächskontext per fester Session; siehe [speaker-to-claude.md](speaker-to-claude.md))
- `run_duplex_claude.sh` — Mikro **+** Lautsprecher-Monitor dauerhaft mithören
  (via `parec`), an Sprechpausen → Claude → Fenster; kein Alt+Alt, kein Cursor-Tippen
  (siehe [duplex-to-claude.md](duplex-to-claude.md))
- `run_meeting.sh` — Meeting: Mikro + Speaker mithören → Markdown-Transkript mit
  Zeitstempeln, Claude erläutert jeden Turn kurz als Stichpunkte im Fenster,
  beim Beenden strukturiertes Protokoll (siehe [meeting.md](meeting.md))
