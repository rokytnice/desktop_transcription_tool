#!/bin/bash
cd "$(dirname "$0")/offline"

# Set default env vars ONLY if -d/--default is passed
if [[ "$*" == *"-d"* ]] || [[ "$*" == *"--default"* ]]; then
    export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
    export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
fi

exec "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
