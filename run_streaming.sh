#!/bin/bash
cd "$(dirname "$0")/offline"
exec "$(pwd)/.venv/bin/python" transcription_streaming.py "$@"
