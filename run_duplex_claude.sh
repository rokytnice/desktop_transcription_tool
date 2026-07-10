#!/bin/bash
#
# run_duplex_claude.sh — Mikrofon UND Lautsprecher dauerhaft mithören → Claude
#
# Schneidet GLEICHZEITIG das Mikrofon (🎤) und den Lautsprecher-Ausgang (🔊,
# über den PipeWire-/PulseAudio-Monitor) mit. An jeder Sprechpause wird die
# erkannte Phrase transkribiert und als Prompt an `claude -p` übergeben; die
# Antwort erscheint live im Hauptfenster. Läuft kontinuierlich — kein Alt+Alt,
# kein Tippen am Cursor.
#
# VERWENDUNG
#   ./run_duplex_claude.sh [OPTIONEN]
#
# OPTIONEN
#   (kein Flag)   Mikrofon + Lautsprecher mithören
#   --no-mic      nur Lautsprecher (Speaker-Monitor) mithören
#   --no-speaker  nur Mikrofon mithören
#   -h, --help    Diese Hilfe anzeigen
#
# UMGEBUNGSVARIABLEN
#   WHISPER_MODEL         tiny | base | small | medium | large  (Standard: small)
#   STREAM_SILENCE_RMS    Schwelle Stille-Erkennung             (Standard: 0.010)
#   DUPLEX_MICRO_SILENCE  kurze Pause → Live-Chunk (Stream) in s (Standard: 0.35)
#   DUPLEX_TURN_SILENCE   längere Pause → Turn an Claude in s    (Standard: 1.1)
#   DUPLEX_MIN_CHUNK      Mindestlänge Live-Chunk in s           (Standard: 0.25)
#   DUPLEX_MAX_TURN       Turn-Notbremse (Monolog) in s          (Standard: 30.0)
#   CLAUDE_CWD            Arbeitsverzeichnis für Claude          (Standard: $HOME)
#   CLAUDE_MODEL          Modell für Claude (z. B. sonnet, opus) (optional)
#   CLAUDE_PERMISSION_MODE  z. B. plan, acceptEdits              (optional)
#   MIC_SOURCE           parec-Quelle Mikro (Standard: @DEFAULT_SOURCE@)
#   SPEAKER_SOURCE       parec-Quelle Monitor (Standard: <default-sink>.monitor)
#
# HINWEIS (Echo)
#   Bei offenen Lautsprechern nimmt das Mikro auch den Speaker-Ton auf →
#   doppelte Phrasen. Kopfhörer nutzen oder eine Quelle mit --no-mic /
#   --no-speaker abschalten.
#
# VORAUSSETZUNG
#   `claude` (Claude Code CLI) eingeloggt, `parec` (pulseaudio-utils) installiert.
#
# BEISPIELE
#   ./run_duplex_claude.sh                 Mikro + Speaker
#   ./run_duplex_claude.sh --no-mic        nur Speaker (z. B. Videocall-Gegenüber)
#   CLAUDE_MODEL=opus ./run_duplex_claude.sh

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

cd "$(dirname "$0")/offline"

RUN_ARGS=("$@")
while true; do
    "$(pwd)/.venv/bin/python" transcription_duplex_claude.py "${RUN_ARGS[@]}"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ]; then
        break
    fi
    echo "⚠️  Crashed (exit code $EXIT_CODE), restarting in 3 seconds..."
    sleep 3
done
