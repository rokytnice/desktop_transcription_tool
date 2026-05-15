#!/bin/bash
cd "$(dirname "$0")"
exec "$(pwd)/.venv/bin/python" transcription_offline.py "$@"
