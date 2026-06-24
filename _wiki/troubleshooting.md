# Troubleshooting

_Zuletzt aktualisiert: 2026-06-24_

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

Betrifft `transcription_streaming.py` und `transcription_faster_streaming.py`.
Der Offline-Modus nutzt Clipboard+Ctrl+V und ist nicht betroffen.

**Wenn ein Keycode falsch wirkt:** Eintrag in `_DE_KEYMAP` korrigieren
(Keycodes = Linux `input-event-codes.h`, US-Position; de interpretiert sie).

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
