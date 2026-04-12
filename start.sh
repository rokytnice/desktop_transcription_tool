#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "================================"
echo "🎙️  Transcription System START"
echo "================================"
echo ""

# Ensure we're in the input group
if ! id -G | grep -q 995; then
    echo "⚠️  Not in input group. Running with newgrp input..."
    exec newgrp input "$0"
fi

echo "✓ Input group: OK"
echo ""

# Check daemon status
echo "Checking daemon..."
if systemctl --user is-active --quiet transcribe; then
    echo "✓ Daemon already running"
else
    echo "Starting daemon..."
    systemctl --user start transcribe
    sleep 2
    echo "✓ Daemon started"
fi

echo ""
echo "Checking ydotoold..."
if sudo systemctl is-active --quiet ydotoold 2>/dev/null; then
    echo "✓ ydotoold running"
else
    echo "⚠️  ydotoold not running (try: sudo systemctl status ydotoold)"
fi

echo ""
echo "================================"
echo "✅ SYSTEM READY!"
echo "================================"
echo ""

echo ""
echo "================================"
echo "📋 LIVE LOGS"
echo "================================"
echo ""
echo "Showing transcribe daemon logs..."
echo "(Press Ctrl+C to stop)"
echo ""

# Show logs
journalctl --user -u transcribe -f --no-hostname -o short-iso 2>/dev/null || \
journalctl --user -u transcribe -f 2>/dev/null || \
echo "Could not open logs"
