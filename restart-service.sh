#!/bin/bash
#
# restart-service.sh — Transcription Service neu starten
#
# VERWENDUNG
#   ./restart-service.sh [OPTIONEN]
#
# OPTIONEN
#   -h, --help   Diese Hilfe anzeigen
#
# BESCHREIBUNG
#   Startet den transcription-offline.service neu und zeigt danach den Status.
#   Kann auch als globales Kommando verwendet werden (nach ./install.sh):
#
#   transcription-restart

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

systemctl --user restart transcription-offline.service
systemctl --user status transcription-offline.service --no-pager
