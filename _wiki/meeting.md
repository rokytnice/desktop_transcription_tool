# Meeting-Modus — Transkript + Live-Stichpunkte + Protokoll

_Zuletzt aktualisiert: 2026-07-13_

Eigenständige Funktion (bewusst getrennt vom VAD-Streaming und vom Duplex-Modus):
`offline/transcription_meeting.py`, Starter `run_meeting.sh`.

## Was passiert

1. **Mithören:** Mikrofon (🎤 Du) und Lautsprecher-Monitor (🔊 Gegenüber)
   werden gleichzeitig über `parec` erfasst (gleiche VAD-Basis wie duplex,
   aber einstufig: nur Turn-Segmentierung, kein Live-Chunk-Stream).
2. **Transkript:** Jeder abgeschlossene Turn wird sofort mit Zeitstempel +
   Sprecher in `~/Dokumente/meetings/YYYY-MM-DD_HHMM_transkript.md` geschrieben.
3. **Live-Erläuterung:** Bei jeder Sprechpause geht der Turn an `claude -p`
   (feste Session pro Meeting → Kontext) mit dem Auftrag: Inhalt **kurz und
   knapp als Stichpunkte** erläutern bzw. gestellte Fragen direkt beantworten
   (max. 3–4 Punkte, „–“ wenn nichts erwähnenswert). Anzeige nur im Fenster —
   kein Tippen am Cursor.
4. **Protokoll:** Beenden (Button „⏹ Meeting beenden + Protokoll“ oder Fenster
   schließen) → eigener Claude-Aufruf ohne Session erzeugt aus dem Transkript
   `..._protokoll.md` (Zusammenfassung, Themen, Entscheidungen, Action Items
   als Checkliste, offene Fragen) und öffnet es per `xdg-open`.

## Start

```bash
transcription meeting        # stoppt den Tipp-Service für die Dauer, startet ihn danach wieder
transcription-mode meeting   # Alias auf dasselbe
./run_meeting.sh [--no-mic | --no-speaker]   # direkt (Service läuft weiter!)
```

`transcription meeting` ist der empfohlene Weg: Der Launcher stoppt laufende
`transcription-*`-Services (sonst tippt der VAD-Service parallel mit, weil beide
das Mikro hören) und startet sie beim Beenden wieder. Geräte-Flags (`-a`, `-d`)
werden für meeting NICHT injiziert — parec nutzt die PipeWire-Default-Quellen.

## Konfiguration (Env)

| Variable | Default | Bedeutung |
|---|---|---|
| `MEETING_TURN_SILENCE` | 1.2 s | Pause → Turn abschließen |
| `MEETING_MIN_TURN` | 0.4 s | kürzere Turns werden verworfen |
| `MEETING_MAX_TURN` | 30 s | Notbremse bei Monolog |
| `MEETING_DIR` | `~/Dokumente/meetings` | Ausgabeverzeichnis |
| `CLAUDE_MODEL` | (leer) | z. B. `haiku` für schnellere Live-Stichpunkte |
| `STREAM_SILENCE_RMS` | 0.010 | Stille-Schwelle (geteilt mit VAD-Modus) |
| `MIC_SOURCE` / `SPEAKER_SOURCE` | Default-Quelle/-Monitor | parec-Quellen |

## Gotchas

- **Echo:** Offene Lautsprecher → Mikro nimmt Speaker-Ton mit auf → doppelte
  Turns. Kopfhörer nutzen oder `--no-mic`/`--no-speaker`.
- Eigener Single-Instance-Lock (`desktop_transcription_meeting.<uid>.lock`),
  unabhängig vom Tipp-Lock der anderen Modi.
- SIGTERM/SIGINT beendet HART ohne Protokoll (Transkript bleibt erhalten) —
  Protokoll gibt es nur über Button/Fensterschließen.
- Claude-Aufrufe sind seriell (`_claude_lock`); bei sehr dichtem Gespräch
  hinken die Stichpunkte dem Transkript hinterher — Transkript ist davon
  unabhängig und immer vollständig.
