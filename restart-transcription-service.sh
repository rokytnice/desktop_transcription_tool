#!/bin/bash
#
# restart-transcription-service.sh — Transcription Service neu starten
#
# VERWENDUNG
#   ./restart-transcription-service.sh [OPTIONEN]
#
# OPTIONEN
#   -h, --help   Diese Hilfe anzeigen
#
# BESCHREIBUNG
#   Startet den installierten Transcription-Service neu und zeigt danach den
#   Status. Die Unit heißt modus-spezifisch (transcription-<modus>.service) und
#   wird automatisch erkannt — egal ob faster-streaming, streaming, offline oder
#   claude eingerichtet ist.
#   Kann auch als globales Kommando verwendet werden (nach ./setup-service.sh):
#
#   transcription-restart

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

# Installierte Transcription-Unit automatisch finden (modus-spezifisch benannt).
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="$(ls -1 "$UNIT_DIR"/transcription-*.service 2>/dev/null | head -1 | xargs -r basename)"
# Fallback auf den alten festen Namen, falls vorhanden.
[[ -z "$SERVICE" && -f "$UNIT_DIR/transcription.service" ]] && SERVICE="transcription.service"

if [[ -z "$SERVICE" ]]; then
    echo "✗ Keine Transcription-Unit gefunden in $UNIT_DIR."
    echo "  Zuerst ./setup-service.sh ausführen."
    exit 1
fi

echo "→ Service: $SERVICE"
systemctl --user restart pipewire wireplumber
systemctl --user restart "$SERVICE"
systemctl --user status "$SERVICE" --no-pager
