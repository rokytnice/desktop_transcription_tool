#!/bin/bash
#
# run_offline.sh — Desktop Transcription Tool starten
#
# VERWENDUNG
#   ./run_offline.sh [OPTIONEN]
#
# OPTIONEN
#   (kein Flag)   Interaktive Geräteauswahl beim Start
#   -a, --auto    Ein Gerät für Input UND Output wählen (z.B. Jabra Headset)
#   -d, --default Schnellstart mit System-Default-Geräten, kein Menü
#   -h, --help    Diese Hilfe anzeigen
#
# UMGEBUNGSVARIABLEN
#   AUDIO_DEVICE          Input-Gerät (Index, überschreibt Auswahl)
#   AUDIO_OUTPUT_DEVICE   Output-Gerät (Index, überschreibt Auswahl)
#   WHISPER_MODEL         tiny | base | small | medium | large  (Standard: small)
#
# BEDIENUNG
#   Alt+Alt   Aufnahme starten / stoppen + transkribieren
#   Ctrl+C    Programm beenden
#
# BEISPIELE
#   ./run_offline.sh                     Interaktive Geräteauswahl
#   ./run_offline.sh -a                  Jabra-Modus: ein Gerät für alles
#   ./run_offline.sh -d                  Schnellstart, kein Menü
#   AUDIO_DEVICE=7 ./run_offline.sh -d   Gerät 7 als Input, Default-Output
#   WHISPER_MODEL=medium ./run_offline.sh  Größeres Modell verwenden

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

cd "$(dirname "$0")/offline"

if [[ "$*" == *"-d"* ]] || [[ "$*" == *"--default"* ]]; then
    export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
    export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
fi

while true; do
    "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ]; then
        break
    fi
    echo "⚠️  Crashed (exit code $EXIT_CODE), restarting in 3 seconds..."
    sleep 3
done
