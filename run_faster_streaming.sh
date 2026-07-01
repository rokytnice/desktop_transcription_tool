#!/bin/bash
#
# run_faster_streaming.sh — Echtes inkrementelles Streaming starten
#
# Anders als run_streaming.sh (VAD: Text erst an der Sprechpause) liefert diese
# Variante Text WORTWEISE WÄHREND des Sprechens. Technik: faster-whisper
# (CTranslate2) + LocalAgreement-2 — ein wachsender Audio-Puffer wird ~jede
# Sekunde neu transkribiert, und nur über zwei Läufe stabile Wörter werden
# festgeschrieben und live an der Cursor-Position getippt.
#
# VERWENDUNG
#   ./run_faster_streaming.sh [OPTIONEN]
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
#   STREAM_MIN_CHUNK      Update-Takt in s (~2s ≈ 3-5 Wörter pro Schub)  (Standard: 2.0)
#   STREAM_MAX_BUFFER     Puffer-Obergrenze in s vor Beschnitt         (Standard: 18.0)
#   STREAM_BEAM           Beam-Size (1 = geringste Latenz)             (Standard: 1)
#   STREAM_KBLAYOUT       Tastaturlayout für ydotool (de|us, sonst Auto-Erkennung)
#
# BEDIENUNG
#   Alt+Alt   Streaming starten / stoppen
#   Ctrl+C    Programm beenden
#
# TIPP
#   Standard-Takt 2s (~3-5 Wörter pro Schub) — 'small' hält auch auf CPU Schritt.
#   Für möglichst wortweise Ausgabe Takt senken + kleineres Modell:
#     STREAM_MIN_CHUNK=1.0 WHISPER_MODEL=base ./run_faster_streaming.sh
#
# BEISPIELE
#   ./run_faster_streaming.sh                      Interaktive Geräteauswahl
#   ./run_faster_streaming.sh -a                   Jabra-Modus: ein Gerät für alles
#   ./run_faster_streaming.sh -d                   Schnellstart, kein Menü
#   WHISPER_MODEL=tiny ./run_faster_streaming.sh   Schnellstes Modell, geringste Latenz

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
    "$(pwd)/.venv/bin/python" transcription_faster_streaming.py "${RUN_ARGS[@]}"
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
