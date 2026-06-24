#!/bin/bash
#
# enable-service.sh — Kompatibilitäts-Wrapper auf setup-service.sh
#
# VERWENDUNG
#   ./enable-service.sh [MODUS] [OPTIONEN]
#   -h, --help   Diese Hilfe anzeigen
#
# BESCHREIBUNG
#   Frühere Versionen installierten nur den Offline-Service. Die Service-
#   Einrichtung läuft jetzt zentral über setup-service.sh (Modus wählbar,
#   Autostart bei Rechnerstart). Dieses Skript reicht alle Argumente einfach
#   an setup-service.sh weiter.
#
#   Beispiele:
#     ./enable-service.sh                  faster-streaming (Standard)
#     ./enable-service.sh offline          klassischer Offline-Modus
#     ./enable-service.sh --help           vollständige Hilfe

exec "$(dirname "$0")/setup-service.sh" "$@"
