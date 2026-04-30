#!/bin/bash

# Quick start script for transcription tool

echo "🎤 Starting Transcription Tool..."
echo ""

cd "$(dirname "$0")"

# Activate venv
source .venv/bin/activate

# Run the transcription tool with sudo
sudo /home/aroc/PycharmProjects/desktop_transcription_tool/.venv/bin/python transcription_offline.py
