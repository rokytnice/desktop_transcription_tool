# Duplex → Claude Code (duplex-Modus)

_Zuletzt aktualisiert: 2026-07-06_

## Was es macht

Hört **kontinuierlich** und **gleichzeitig** zwei Audioquellen mit, segmentiert
beide **zweistufig** (siehe unten) und schickt jeden Turn an dieselbe
Claude-Session; die Transkription **und** die Antwort erscheinen live im
Tkinter-Hauptfenster. Kein Alt+Alt, kein Tippen am Cursor — läuft von allein.

- 🎤 **Mikrofon** — Default-Aufnahmequelle (`@DEFAULT_SOURCE@`)
- 🔊 **Lautsprecher** — PipeWire-/PulseAudio-**Monitor** des Default-Sinks
  (`<sink>.monitor`), also alles was aus den Boxen kommt (Videocall-Gegenüber,
  Video, Podcast …)

Dateien:
- `offline/transcription_duplex_claude.py` — Modus-Logik + GUI
- `run_duplex_claude.sh` — Wrapper (Auto-Restart, KEINE Geräteauswahl-Flags)
- `start.sh duplex` / Menü-Punkt 5

## Architektur — warum parec statt sounddevice (GOTCHA)

Der Speaker-Ausgang lässt sich **nicht** über die sounddevice/PortAudio-Geräte­
auswahl abgreifen — Monitor-Quellen tauchen dort nicht zuverlässig auf. Deshalb
werden **beide** Quellen über `parec` (pulseaudio-utils) gelesen:

```
parec --format=float32le --rate=16000 --channels=1 --device=<source> --latency-msec=100
```

Das liefert rohes Float32-Mono PCM auf stdout (kein Header). Pro 0.1-s-Block
werden `BLOCKSIZE*4 = 6400` Bytes gelesen und mit `np.frombuffer(dtype=float32)`
direkt in ein Array gewandelt — dasselbe Format, das Whisper/`transcribe_chunk`
erwartet. `parec` hält einen SUSPENDED-Monitor automatisch am Laufen (RUNNING),
solange der Client liest; bei Stille kommen Null-Blöcke (RMS 0) → korrekt als
Pause erkannt. Bricht die Quelle weg (EOF), verbindet die `VADSource` nach 1 s neu.

Quellen ermitteln: `pactl get-default-source` bzw. `pactl get-default-sink` +
`.monitor`. Override per `MIC_SOURCE` / `SPEAKER_SOURCE`.

## Zweistufiges VAD — Stream via Mikro-Pausen (Kernidee)

Damit der Text als **Stream** erscheint (nicht erst als ganzer Block an einer
langen Pause), segmentiert `VADSource.run()` in zwei Stufen:

1. **Mikro-Pause** (`DUPLEX_MICRO_SILENCE`, Standard 0.35 s): schon eine kurze
   Sprechpause schließt einen **Live-Chunk** ab → `base.transcribe_chunk` →
   sofort per `("live", …)`-Event ins Fenster gestreamt. Der Chunk-Text wird
   zusätzlich im laufenden **Turn** gesammelt (`utter_texts`).
2. **Turn-Ende** (`DUPLEX_TURN_SILENCE`, Standard 1.1 s): erst eine längere Pause
   beendet den Turn; der gesammelte Text geht als **ein** Prompt an Claude
   (`phrase_queue`). So antwortet Claude auf einen zusammenhängenden Beitrag statt
   auf jedes 3-Wort-Fragment. Wer bewusst pro Mikro-Chunk an Claude will, setzt
   `DUPLEX_TURN_SILENCE` gleich `DUPLEX_MICRO_SILENCE`.

Notbremsen: `MAX_PHRASE` (Mikro-Chunk ohne jede Pause) und `DUPLEX_MAX_TURN`
(langer Monolog → Turn wird trotzdem geflusht). `SILENCE_RMS`, `MAX_PHRASE`,
`transcribe_chunk`, `get_whisper_model` kommen weiterhin aus
`transcription_streaming as base` — Whisper wird nur **einmal** geladen und von
beiden Quellen geteilt.

**GUI-Streaming:** Der `live`-Event hängt Text fortlaufend an; das Quell-Label
(🎤/🔊) wird nur bei Quellenwechsel/Zeilenanfang gesetzt (`_live_label`). Der
Turn-Text wird deshalb **nicht** erneut als Block gezeigt, wenn er an Claude geht
— er steht bereits gestreamt im Fenster.

## Serialisierung: EINE Claude-Session, nie zwei Aufrufe parallel (GOTCHA)

Beide Quellen laufen als eigene Threads und können **gleichzeitig** eine Phrase
fertigstellen. Würde jede direkt `claude` aufrufen, kollidierten zwei
`--resume <same-uuid>`-Aufrufe auf derselben Session. Deshalb:

- Jede fertige Phrase → `phrase_queue.put((label, text))`
- Ein einzelner `claude_worker`-Thread nimmt sie **eine nach der anderen** ab
- `ask_claude` zusätzlich per `_claude_lock` geschützt
- Session-Handling wie im claude-Modus: 1. Turn `--session-id`, danach `--resume`
  (`_first_turn`-Flag). Prompt wird mit `[🎤 Mikro:]` / `[🔊 Speaker:]` geprefixt,
  damit Claude die Quelle einordnen kann.

## Threading → GUI

Wie im claude-Modus schieben die Worker Events (`status`/`live`/`claude_start`/
`claude_chunk`/`claude_end`) in eine `queue.Queue`; `DuplexWindow` pollt sie per
`root.after(80, …)` auf dem Hauptthread (Tkinter ist nicht thread-sicher).
`live`-Payload ist `(label, text)` — die GUI färbt Mikro blau, Speaker gelb und
hängt den Text gestreamt an.

## Single-Instance — eigener Lock

Nutzt **nicht** den Cursor-Tipp-Lock der anderen Modi (`_singleinstance.py`),
weil dieser Modus nicht am Cursor tippt und die Geräte per parec teilt (mehrere
parec-Clients auf derselben Quelle sind erlaubt). Stattdessen eigener flock auf
`$XDG_RUNTIME_DIR/desktop_transcription_duplex.<uid>.lock` → verhindert nur, dass
zwei Duplex-Instanzen Claude-Turns verdoppeln. Läuft damit **parallel** zum
vad-Service ohne Konflikt.

## Echo (bekanntes Verhalten)

Bei offenen Lautsprechern nimmt das Mikro auch den Speaker-Ton auf → dieselbe
Äußerung kann doppelt ankommen (Mikro **und** Monitor). Keine Echo-Cancellation
implementiert. Abhilfe: Kopfhörer, oder eine Quelle per `--no-mic` /
`--no-speaker` abschalten.

## Konfiguration (Env)

| Variable | Default | Zweck |
|---|---|---|
| `WHISPER_MODEL` | `small` | Whisper-Modell |
| `STREAM_SILENCE_RMS` | wie vad-Modus | Schwelle Stille-Erkennung |
| `DUPLEX_MICRO_SILENCE` | `0.35` | kurze Pause → Live-Chunk (Stream) in s |
| `DUPLEX_TURN_SILENCE` | `1.1` | längere Pause → Turn an Claude in s |
| `DUPLEX_MIN_CHUNK` | `0.25` | Mindestlänge eines Live-Chunks in s |
| `DUPLEX_MAX_TURN` | `30.0` | Turn-Notbremse (Monolog) in s |
| `CLAUDE_CWD` / `CLAUDE_MODEL` / `CLAUDE_PERMISSION_MODE` | wie claude-Modus | Claude-CLI |
| `MIC_SOURCE` | `@DEFAULT_SOURCE@` | parec-Quelle Mikro |
| `SPEAKER_SOURCE` | `<default-sink>.monitor` | parec-Quelle Monitor |

## Voraussetzung

`claude`-CLI eingeloggt **und** `parec` (Paket `pulseaudio-utils`) im PATH. Der
Start prüft beides und bricht mit klarer Meldung ab. GUI braucht XWayland
(`DISPLAY`) wie der claude-Modus. Siehe [[speaker-to-claude]] für die geteilten
Claude-/Session-Grundlagen.
