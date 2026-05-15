#!/bin/bash
cd "$(dirname "$0")/offline"
export AUDIO_DEVICE=${AUDIO_DEVICE:-0}
export AUDIO_OUTPUT_DEVICE=${AUDIO_OUTPUT_DEVICE:-19}
exec "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
