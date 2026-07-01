#!/bin/bash
#
# run_claude.sh — Sprich mit Claude Code (Sprache → claude -p → Fenster)
#
# Statt den transkribierten Text an der Cursor-Position zu tippen, wird er als
# Prompt an die Claude-Code-CLI übergeben. Claudes Antwort erscheint live in
# einem eigenen Fenster. Über eine feste Session bleibt der Gesprächskontext
# über mehrere Sprach-Eingaben hinweg erhalten.
#
# VERWENDUNG
#   ./run_claude.sh [OPTIONEN]
#
# OPTIONEN
#   (kein Flag)   Interaktive Geräteauswahl beim Start
#   -a, --auto    Ein Gerät für Input UND Output wählen (z.B. Jabra Headset)
#   -d, --default Schnellstart mit System-Default-Geräten, kein Menü
#   -h, --help    Diese Hilfe anzeigen
#
# UMGEBUNGSVARIABLEN
#   AUDIO_DEVICE          Input-Gerät (Index, überschreibt Auswahl)
#   AUDIO_OUTPUT_DEVICE   Output-Gerät (Index, für Beeps)
#   WHISPER_MODEL         tiny | base | small | medium | large  (Standard: small)
#   CLAUDE_CWD            Arbeitsverzeichnis für Claude          (Standard: $HOME)
#   CLAUDE_MODEL          Modell für Claude (z. B. sonnet, opus) (optional)
#   CLAUDE_PERMISSION_MODE  z. B. plan, acceptEdits              (optional)
#
# BEDIENUNG
#   Alt+Alt   Aufnahme starten / stoppen → an Claude übergeben
#   Ctrl+C / Fenster schließen   Beenden
#
# VORAUSSETZUNG
#   `claude` (Claude Code CLI) muss installiert und eingeloggt sein.
#
# BEISPIELE
#   ./run_claude.sh                      Interaktive Geräteauswahl
#   ./run_claude.sh -a                   Jabra-Modus: ein Gerät für alles
#   CLAUDE_CWD=~/projects ./run_claude.sh   Claude im Projektordner laufen lassen
#   CLAUDE_MODEL=opus ./run_claude.sh    Opus-Modell verwenden

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

cd "$(dirname "$0")/offline"

if [[ "$*" == *"-d"* ]] || [[ "$*" == *"--default"* ]]; then
    export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
    export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
fi

RUN_ARGS=("$@")
while true; do
    "$(pwd)/.venv/bin/python" transcription_claude.py "${RUN_ARGS[@]}"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ]; then
        break
    fi
    if [ $EXIT_CODE -eq 75 ]; then
        # Eingabegerät verloren → nicht-interaktiv mit Default-Geräten neu starten
        case " ${RUN_ARGS[*]} " in
            *" -a "*|*" --auto "*|*" -d "*|*" --default "*) : ;;
            *) RUN_ARGS+=("-d") ;;
        esac
        export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
        export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
        echo "🔁 Eingabegerät verloren — Neustart mit Default-Einstellungen..."
        sleep 1
        continue
    fi
    echo "⚠️  Crashed (exit code $EXIT_CODE), restarting in 3 seconds..."
    sleep 3
done
