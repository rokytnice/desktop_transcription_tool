#!/bin/bash
#
# run_streaming.sh — Echtzeit-Streaming-Transkription starten
#
# Transkribiert KONTINUIERLICH während des Sprechens und tippt den Text live
# an der Cursor-Position (via ydotool auf GNOME, wtype auf wlroots; sonst
# Zwischenablage). Es wird nicht auf das Ende der Eingabe gewartet — an jeder
# Sprechpause erscheint die erkannte Phrase.
#
# VERWENDUNG
#   ./run_streaming.sh [OPTIONEN]
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
#   STREAM_SILENCE_RMS    Schwelle Stille-Erkennung               (Standard: 0.010)
#   STREAM_MIN_SILENCE    Pausenlänge in s bis Phrase getippt wird (Standard: 0.7)
#   STREAM_MIN_PHRASE     Minimale Phrasenlänge in s              (Standard: 0.4)
#   STREAM_MAX_PHRASE     Max. Phrasenlänge in s ohne Pause       (Standard: 15.0)
#
# BEDIENUNG
#   Alt+Alt   Streaming starten / stoppen
#   Ctrl+C    Programm beenden
#
# TIPP
#   Für geringste Latenz ein kleineres Modell verwenden:
#     WHISPER_MODEL=tiny ./run_streaming.sh
#
# BEISPIELE
#   ./run_streaming.sh                      Interaktive Geräteauswahl
#   ./run_streaming.sh -a                   Jabra-Modus: ein Gerät für alles
#   ./run_streaming.sh -d                   Schnellstart, kein Menü
#   WHISPER_MODEL=tiny ./run_streaming.sh   Schnellstes Modell, geringste Latenz

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
    "$(pwd)/.venv/bin/python" transcription_streaming.py "$@"
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ]; then
        break
    fi
    echo "⚠️  Crashed (exit code $EXIT_CODE), restarting in 3 seconds..."
    sleep 3
done
