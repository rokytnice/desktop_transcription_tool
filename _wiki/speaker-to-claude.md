# Sprich mit Claude Code (claude-Modus)

_Zuletzt aktualisiert: 2026-06-24_

## Was es macht

Sprache → Whisper-Transkript → als Prompt an die Claude-Code-CLI (`claude -p`)
→ Claudes Antwort erscheint live in einem Tkinter-Fenster. Statt den Text an der
Cursor-Position zu tippen, wird ein echtes Sprach-Gespräch mit Claude geführt.

Dateien:
- `offline/transcription_claude.py` — Modus-Logik + GUI
- `run_claude.sh` — Wrapper (Geräteauswahl, Auto-Restart)
- `setup-service.sh claude` — Autostart-Service

## Architektur — Wiederverwendung per Monkeypatch

`transcription_claude.py` importiert `transcription_offline as base` und ersetzt
nur die **Ausgabe**:

```python
base.start_recording      = _start_recording_hook   # nur Status-Update + Original
base.transcribe_and_output = transcribe_and_output    # Clipboard → Claude → Fenster
```

Das funktioniert, weil die Alt+Alt-Logik in `base` (`monitor_device` /
`stop_recording`) diese Namen **zur Laufzeit als Modul-Globals** auflöst — das
Neuzuweisen der Attribute auf dem `base`-Modul greift also durch. Aufnahme,
Whisper, Geräteauswahl, Tastatur-Erkennung bleiben unverändert.

`transcribe_and_output()` läuft im Worker-Thread und schiebt Events
(`status`/`user`/`claude_start`/`claude_chunk`/`claude_end`) in eine
`queue.Queue`. Die GUI (`ChatWindow`) pollt diese Queue per `root.after(80, …)`
auf dem **Hauptthread** — Tkinter ist nicht thread-sicher, deshalb diese Brücke.

## Session-Kontext: --session-id vs. --resume (GOTCHA)

Pro Lauf wird **eine** `SESSION_ID` (UUID) erzeugt. Damit der Kontext über
mehrere Sprach-Eingaben erhalten bleibt:

- **1. Turn:** `claude -p --session-id <uuid> <prompt>` → legt die Session **an**
- **Folge-Turns:** `claude -p --resume <uuid> <prompt>` → setzt sie **fort**

Wichtig: `--session-id` mit einer **bereits existierenden** ID erneut aufzurufen
gibt `Error: Session ID … is already in use.` — daher der Wechsel auf `--resume`
ab dem zweiten Turn (`_first_turn`-Flag).

## GUI braucht XWayland (DISPLAY)

Das Tk-Fenster läuft über XWayland und braucht `DISPLAY` (meist `:0`). Beim
manuellen Start ist das in der Desktop-Sitzung gesetzt. Als Service setzt
`setup-service.sh` zusätzlich `Environment="DISPLAY=$X_DISPLAY"`
(`X_DISPLAY="${DISPLAY:-:0}"`) in der generierten Unit — sonst startet das
Fenster nicht.

## Konfiguration (Env)

| Variable | Default | Zweck |
|---|---|---|
| `WHISPER_MODEL` | `small` | Whisper-Modell |
| `CLAUDE_CWD` | `$HOME` | Arbeitsverzeichnis von Claude |
| `CLAUDE_MODEL` | — | z. B. `opus`, `sonnet` |
| `CLAUDE_PERMISSION_MODE` | — | z. B. `plan`, `acceptEdits` |

## Voraussetzung

Die `claude`-CLI (Claude Code) muss installiert und eingeloggt sein. Der Start
prüft `which claude` und bricht mit klarer Meldung ab, wenn sie fehlt.
