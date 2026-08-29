# Projekt-Wiki — Desktop Transcription Tool

_Zuletzt aktualisiert: 2026-07-21_

## Inhalt
- [service.md](service.md) — Service-Setup & Autostart bei Rechnerstart
- [speaker-to-claude.md](speaker-to-claude.md) — Sprich mit Claude Code (claude-Modus)
- [duplex-to-claude.md](duplex-to-claude.md) — Mikro + Speaker dauerhaft → Claude (duplex-Modus)
- [meeting.md](meeting.md) — Meeting: Transkript + Live-Stichpunkte + Protokoll (meeting-Modus)
- [troubleshooting.md](troubleshooting.md) — bekannte Probleme, Diagnose, Fix

## Kurzüberblick
**Keine automatischen Satzpunkte:** Whisper setzt am Ende jeder erkannten Phrase
einen Punkt — beim Live-Diktat also nach jeder Sprechpause. `_typer.strip_auto_periods()`
entfernt Punkte am Wort-/Zeilenende in allen Diktat-Modi (offline, streaming,
faster_streaming); Punkte mitten im Wort (`1.5`, `z.B.`, `foo.py`) bleiben.
`AUTO_PERIODS=1` stellt das alte Verhalten wieder her.

Aufnahme → Whisper-Transkription → Text wird an der Cursor-Position getippt,
ausgelöst per Alt+Alt-Doppeltipp (Wayland/GNOME). Sechs Modi:
- `run_offline.sh` — Aufnahme, Transkription **am Ende** (Standard): Alt+Alt
  stoppt, dann wird die ganze Aufnahme am Stück transkribiert und getippt.
  Aufnahme fest 16 kHz mono float32 (whisper-nativ), WAV wird gesichert.
  Tipp-Backend `_typer.py` (Clipboard nur Fallback).
  **Live-Pipelining** ist opt-in per `OFFLINE_LIVE=1`: ein Hintergrund-Worker
  transkribiert Phrasen an Sprechpausen (VAD) schon während der Aufnahme und
  tippt sie sofort. Bewusst nicht Standard — das zerlegt das Diktat in
  Phrasen-Häppchen (André, 2026-08-14). Segment-Tuning teilt sich die
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
