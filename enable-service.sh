#!/bin/bash
set -e

SERVICE="transcription-offline.service"
SERVICE_SRC="$(dirname "$0")/transcription-offline.service"
SERVICE_DST="$HOME/.config/systemd/user/$SERVICE"

echo "Installing $SERVICE..."

mkdir -p "$HOME/.config/systemd/user"
cp "$SERVICE_SRC" "$SERVICE_DST"

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE"

echo "✓ Service enabled and started."
echo ""
systemctl --user status "$SERVICE" --no-pager
