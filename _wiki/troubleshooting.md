# Troubleshooting

_Zuletzt aktualisiert: 2026-07-11_

## ydotool tippt Z als Y / falsche Umlaute (deutsches Layout)

**Symptom:** Live-getippter Text vertauscht Z↔Y, Umlaute/Sonderzeichen sind
falsch. Das **Log ist korrekt** — nur die getippte Ausgabe nicht.

**Ursache:** ydotool sendet rohe US-QWERTY-Keycodes ("we're using raw keycodes
now", steht so in `ydotool key --help`). Der GNOME-Compositor interpretiert
diese Keycodes auf dem aktiven **deutschen QWERTZ-Layout** → Z und Y liegen
physisch vertauscht, Umlaute liegen auf anderen Keycodes. `ydotool type` hat
**keine** Layout-Option.

**Fix (umgesetzt, ab v1.6.1):** Bei aktivem de-Layout sendet
`type_at_cursor()` die Keycodes für die **deutsche Belegung** via `ydotool key`
(vollständige T1-Keymap `_DE_KEYMAP`, inkl. äöüß, @, €). Typografische Zeichen
(„ " – …) werden über `_NORMALIZE` auf tippbare gefaltet. Layout-Erkennung:
`detect_kb_layout()` (GNOME `org.gnome.desktop.input-sources` → `localectl`),
überschreibbar per `STREAM_KBLAYOUT=de|us`.

Betrifft alle Modi: `transcription_streaming.py`,
`transcription_faster_streaming.py` (je eigene Inline-Kopie) und seit v1.9.0 auch
den Offline-Modus, der das gemeinsame Modul `offline/_typer.py` nutzt (gleiche
Keymap/Logik). Der Offline-Modus tippt jetzt direkt am Cursor statt nur in die
Zwischenablage; Clipboard ist nur noch Fallback, wenn kein Tipp-Tool da ist.

**Wenn ein Keycode falsch wirkt:** Eintrag in `_DE_KEYMAP` korrigieren
(Keycodes = Linux `input-event-codes.h`, US-Position; de interpretiert sie).

## Getippter Text erscheint doppelt/vielfach — Log aber sauber

**Symptom:** Das Logfile (`~/.transcription/*.log`) zeigt die Transkription
sauber, am Cursor erscheint der Text aber **mehrfach**. Im Log tauchen Zeilen
wie `DOUBLE-TAP DETECTED`, `Streaming started`, `Streaming stopped` **doppelt**
mit identischem Zeitstempel auf.

**Ursache:** Es liefen **zwei Transcription-Instanzen gleichzeitig** — typisch
der systemd-Service **und** ein manuell gestartetes `./run_*.sh`. Beide
überwachen dieselben Tastatur-Devices, erkennen denselben Alt+Alt-Doppeltipp,
transkribieren dieselbe Audio und tippen beide am Cursor. Jede Instanz loggt für
sich sauber — sie kollidieren nur beim Tippen.

**Diagnose:**
```bash
ps -eo pid,etime,cmd | grep -E "transcription_.*\.py" | grep -v grep
# Mehr als eine Zeile? → zwei Instanzen. Eine ist meist der Service (mit -a),
# die andere ein manueller Run (PPID = run_*.sh).
```

**Fix (ab v1.7.1):** Single-Instance-Sperre in `offline/_singleinstance.py`
(`flock` auf `$XDG_RUNTIME_DIR/desktop_transcription.<uid>.lock`). Alle drei
Modi rufen `_singleinstance.acquire_or_exit()` direkt nach dem Argument-Parsen
auf. Systemweit darf nur EINE Instanz laufen; ein zweiter Start bricht sofort
sauber ab (Exit 0) und nennt die PID des Halters. Der `flock` wird vom OS beim
Prozess-Ende automatisch freigegeben (auch bei Crash/kill) — keine
verwaisten Lockfiles. **Manuell testen statt Service?** Erst `transcription-stop`,
dann `./run_*.sh`.

## Start über `start.sh` im Terminal „hängt" — Alt+Alt tut nichts

**Symptom:** Man startet einen Modus über `./start.sh` (z. B. offline) in einem
Terminal. Das Log endet bei `Whisper small model loaded` — **keine** Zeilen
`Auto-selected device` / `Monitoring device` folgen. Alt+Alt löst nichts aus.
Als Service (Autostart) läuft derselbe Modus dagegen einwandfrei.

**Ursache:** `start.sh` reichte für den Schnellstart bloß `-a` durch. `-a`
**allein** bedeutet in der Python-Logik `interactive=True`; ist stdin ein TTY
(Terminal!), zeigt `select_auto_device()` ein **Geräteauswahl-Menü** und
blockiert bei `input()`. Das Menü geht nur nach **stdout**, nicht ins Logfile —
darum sieht das Log wie ein Hänger nach dem Modell-Load aus. Der
Keyboard-Listener wird nie gestartet, also bleibt Alt+Alt wirkungslos. Der
systemd-Service hat **kein** TTY → nimmt den nicht-interaktiven Zweig → läuft.
(Auch der Auto-Restart nach Device-Verlust hängt `-d` an und ist deshalb ok.)

**Diagnose:**
```bash
# Prozess da, aber Log endet bei "Whisper ... loaded"?
tail /home/aroc/.transcription/transcription_listener.log
# Hauptthread in wait_woken (poll/read) + kein "Monitoring device" → wartet auf input()
```

**Fix (start.sh):** Der Default-Pfad ist jetzt `-a -d` statt nur `-a` — also
nicht-interaktiv, ein Default-Gerät für Input+Output, kein Menü (identisch zum
Auto-Restart-Verhalten der `run_*.sh`). Wer bewusst ein Gerät wählen will,
nutzt `./start.sh <modus> --menu`. Betrifft alle nicht-Duplex-Modi (offline,
stream, vad, claude), die dieselbe `-a`-ohne-`-d`-TTY-Falle teilten.

## Beim Stoppen geht der letzte Satzrest verloren (faster-streaming)

**Symptom:** Beim Stoppen (Alt+Alt) fehlten die zuletzt gesprochenen Wörter.

**Ursache:** LocalAgreement-2 schreibt nur Wörter fest, die über **zwei**
Transkriptionsläufe stabil sind. Der letzte Chunk hat keinen zweiten Lauf mehr,
und `finish()` gab früher nur den letzten unbestätigten Hypothesen-Puffer zurück.

**Fix (ab v1.6.1):** `OnlineASRProcessor.finish()` macht einen finalen
Transkriptionslauf über das Rest-Audio und gibt ALLE noch nicht getippten
Wörter aus. `stop()` schließt zuerst den Stream, der Worker drained die Queue,
dann `finish()`, danach der Stop-Beep — so ist die Ausgabe garantiert komplett,
bevor der „fertig"-Ton kommt.
