#!/bin/bash
#
# start.sh — Desktop Transcription Tool starten (EIN Script für alle Modi)
#
# VERWENDUNG
#   ./start.sh                 Interaktives Menü: Modus auswählen
#   ./start.sh <modus> [opts]  Direkt einen Modus starten
#
# MODI
#   offline    Aufnehmen → Alt+Alt stoppen → Text wird am Cursor getippt
#   stream     Wortweise live beim Sprechen (faster-whisper)
#   vad        Streaming an jeder Sprechpause (Voice Activity Detection)  [Standard]
#   claude     Sprache → Claude Code → Antwort im Fenster
#
# OPTIONEN (werden an das jeweilige run_*.sh durchgereicht)
#   (kein Flag)   -a: ein Gerät für Input+Output (z.B. Jabra-Headset)
#   --menu        interaktive Geräteauswahl (statt -a)
#   -d            Schnellstart mit Default-Geräten, kein Geräte-Menü
#   -h, --help    Diese Hilfe anzeigen
#
# BEISPIELE
#   ./start.sh                 Menü zeigen, Modus per Zahl wählen
#   ./start.sh offline         Offline-Modus direkt starten
#   ./start.sh vad --menu      VAD-Streaming mit Geräteauswahl
#   ./start.sh stream -d       Streaming, Default-Geräte, kein Menü

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

REPO="$(cd "$(dirname "$0")" && pwd)"

# ── Modus bestimmen ──────────────────────────────────────────────────────────
MODE=""
case "${1:-}" in
    offline|stream|vad|claude) MODE="$1"; shift ;;
esac

if [[ -z "$MODE" ]]; then
    echo "╭─────────────────────────────────────────────╮"
    echo "│  🎤  Desktop Transcription Tool — Modus?     │"
    echo "├─────────────────────────────────────────────┤"
    echo "│  1) offline   aufnehmen → stoppen → am Cursor │"
    echo "│  2) stream    wortweise live                  │"
    echo "│  3) vad       an Sprechpausen  (Standard)     │"
    echo "│  4) claude    Sprache → Claude Code           │"
    echo "╰─────────────────────────────────────────────╯"
    read -rp "Auswahl [1-4, Enter=3]: " choice
    case "${choice:-3}" in
        1) MODE="offline" ;;
        2) MODE="stream" ;;
        3|"") MODE="vad" ;;
        4) MODE="claude" ;;
        *) echo "✗ Ungültige Auswahl: $choice"; exit 1 ;;
    esac
fi

case "$MODE" in
    offline) SCRIPT="run_offline.sh" ;;
    stream)  SCRIPT="run_faster_streaming.sh" ;;
    vad)     SCRIPT="run_streaming.sh" ;;
    claude)  SCRIPT="run_claude.sh" ;;
esac

# ── Laufenden Service stoppen (sonst doppeltes Tippen) ───────────────────────
for unit in "$HOME"/.config/systemd/user/transcription-*.service; do
    [[ -e "$unit" ]] || continue
    name="$(basename "$unit")"
    if systemctl --user is-active --quiet "$name"; then
        echo "→ stoppe laufenden Service: $name"
        systemctl --user stop "$name"
    fi
done

# ── Geräteauswahl: ohne Flag standardmäßig -a, --menu überspringt das ────────
if [[ $# -eq 0 ]]; then
    set -- -a
elif [[ "${1:-}" == "--menu" ]]; then
    shift
fi

echo "→ Modus: $MODE  ($SCRIPT)"
exec "$REPO/$SCRIPT" "$@"
