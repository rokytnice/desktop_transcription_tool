#!/bin/bash
#
# run_meeting.sh — Meeting-Modus: Transkript + Live-Stichpunkte + Protokoll
#
# Hört GLEICHZEITIG Mikrofon (🎤 Du) und Lautsprecher (🔊 Gegenüber) mit.
# Jeder Gesprächs-Turn landet mit Zeitstempel im Markdown-Transkript; bei
# jeder Sprechpause erläutert Claude den Inhalt kurz als Stichpunkte im
# Fenster (bzw. beantwortet gestellte Fragen). Beim Beenden erzeugt Claude
# aus dem Transkript ein strukturiertes Protokoll (Themen, Entscheidungen,
# Action Items, Zusammenfassung).
#
# AUSGABE
#   ~/Dokumente/meetings/YYYY-MM-DD_HHMM_transkript.md
#   ~/Dokumente/meetings/YYYY-MM-DD_HHMM_protokoll.md
#
# VERWENDUNG
#   ./run_meeting.sh [OPTIONEN]
#
# OPTIONEN
#   (kein Flag)   Mikrofon + Lautsprecher mithören
#   --no-mic      nur Lautsprecher (z. B. Videocall-Gegenüber) mithören
#   --no-speaker  nur Mikrofon mithören
#   -h, --help    Diese Hilfe anzeigen
#
# UMGEBUNGSVARIABLEN
#   WHISPER_MODEL          tiny | base | small | medium | large (Standard: small)
#   STREAM_SILENCE_RMS     Schwelle Stille-Erkennung            (Standard: 0.010)
#   MEETING_TURN_SILENCE   Pause → Turn abschließen in s        (Standard: 1.2)
#   MEETING_MIN_TURN       Mindestlänge Turn in s               (Standard: 0.4)
#   MEETING_MAX_TURN       Turn-Notbremse (Monolog) in s        (Standard: 30.0)
#   MEETING_DIR            Ausgabeverzeichnis                   (Standard: ~/Dokumente/meetings)
#   CLAUDE_MODEL           Modell für Claude (z. B. haiku)      (optional)
#   MIC_SOURCE             parec-Quelle Mikro                   (Standard: @DEFAULT_SOURCE@)
#   SPEAKER_SOURCE         parec-Quelle Monitor                 (Standard: <default-sink>.monitor)
#
# HINWEIS (Echo)
#   Bei offenen Lautsprechern nimmt das Mikro auch den Speaker-Ton auf →
#   doppelte Turns. Kopfhörer nutzen oder eine Quelle abschalten.
#
# VORAUSSETZUNG
#   `claude` (Claude Code CLI) eingeloggt, `parec` (pulseaudio-utils) installiert.

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

cd "$(dirname "$0")/offline"

exec "$(pwd)/.venv/bin/python" transcription_meeting.py "$@"
