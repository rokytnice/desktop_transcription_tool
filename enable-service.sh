#!/bin/bash
#
# enable-service.sh — systemd User-Service installieren und aktivieren
#
# VERWENDUNG
#   ./enable-service.sh [OPTIONEN]
#
# OPTIONEN
#   -h, --help   Diese Hilfe anzeigen
#
# BESCHREIBUNG
#   Kopiert transcription-offline.service nach ~/.config/systemd/user/,
#   aktiviert den Service (Autostart bei Login) und startet ihn sofort.
#   Nach der Einrichtung läuft der Service automatisch bei jedem Login.
#
# NACH DER INSTALLATION
#   transcription-restart   Service neu starten
#   transcription-start     Service starten
#   transcription-stop      Service stoppen
#   transcription-status    Status anzeigen

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

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
