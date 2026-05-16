#!/bin/bash
cd "$(dirname "$0")/offline"

# Set default env vars ONLY if -d/--default is passed
if [[ "$*" == *"-d"* ]] || [[ "$*" == *"--default"* ]]; then
    export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
    export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
fi

# Run with auto-restart on unexpected exit
while true; do
    "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
    EXIT_CODE=$?
    # Exit cleanly on Ctrl+C (exit code 0 or 130)
    if [ $EXIT_CODE -eq 0 ] || [ $EXIT_CODE -eq 130 ]; then
        break
    fi
    echo "⚠️  Crashed (exit code $EXIT_CODE), restarting in 3 seconds..."
    sleep 3
done
