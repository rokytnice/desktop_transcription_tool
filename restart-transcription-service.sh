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
#   Startet den transcription.service neu und zeigt danach den Status.
#   Kann auch als globales Kommando verwendet werden (nach ./install.sh):
#
#   transcription-restart

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

systemctl --user restart pipewire wireplumber
systemctl --user restart transcription.service
systemctl --user status transcription.service --no-pager
