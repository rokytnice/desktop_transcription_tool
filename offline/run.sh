#!/bin/bash

# Quick start script for transcription tool

echo "🎤 Starting Transcription Tool..."
echo ""

cd "$(dirname "$0")"

# Run the transcription tool with sudo (preserve environment)
sudo -E "$(pwd)/.venv/bin/python" transcription_offline.py
