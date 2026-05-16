#!/bin/bash
cd "$(dirname "$0")/offline"

# Only set default env vars if NOT using interactive mode (-H)
if [[ "$*" != *"-H"* ]] && [[ "$*" != *"--interactive"* ]]; then
    export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
    export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
fi

exec "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
