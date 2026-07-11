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
#   duplex     Mikro + Lautsprecher dauerhaft mithören → Claude → Fenster
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
    offline|stream|vad|claude|duplex) MODE="$1"; shift ;;
esac

if [[ -z "$MODE" ]]; then
    echo "╭─────────────────────────────────────────────╮"
    echo "│  🎤  Desktop Transcription Tool — Modus?     │"
    echo "├─────────────────────────────────────────────┤"
    echo "│  1) offline   aufnehmen → stoppen → am Cursor │"
    echo "│  2) stream    wortweise live                  │"
    echo "│  3) vad       an Sprechpausen  (Standard)     │"
    echo "│  4) claude    Sprache → Claude Code           │"
    echo "│  5) duplex    Mikro + Speaker → Claude        │"
    echo "╰─────────────────────────────────────────────╯"
    read -rp "Auswahl [1-5, Enter=3]: " choice
    case "${choice:-3}" in
        1) MODE="offline" ;;
        2) MODE="stream" ;;
        3|"") MODE="vad" ;;
        4) MODE="claude" ;;
        5) MODE="duplex" ;;
        *) echo "✗ Ungültige Auswahl: $choice"; exit 1 ;;
    esac
fi

case "$MODE" in
    offline) SCRIPT="run_offline.sh" ;;
    stream)  SCRIPT="run_faster_streaming.sh" ;;
    vad)     SCRIPT="run_streaming.sh" ;;
    claude)  SCRIPT="run_claude.sh" ;;
    duplex)  SCRIPT="run_duplex_claude.sh" ;;
esac

# ── Laufenden Service stoppen (sonst doppeltes Tippen) ───────────────────────
# Gestoppte Units merken → beim Beenden des manuellen Runs wieder hochfahren.
STOPPED_UNITS=()
for unit in "$HOME"/.config/systemd/user/transcription-*.service; do
    [[ -e "$unit" ]] || continue
    name="$(basename "$unit")"
    # is-active meldet bei einem gerade (neu) startenden Service "activating" —
    # dann greift --quiet nicht. Deshalb jeden nicht-inaktiven Zustand stoppen,
    # sonst blockiert der flappende Service den Single-Instance-Lock.
    state="$(systemctl --user is-active "$name" 2>/dev/null)"
    case "$state" in
        active|activating|reloading|deactivating)
            echo "→ stoppe laufenden Service: $name ($state)"
            systemctl --user stop "$name"
            STOPPED_UNITS+=("$name")
            ;;
    esac
done

# Beim Verlassen (normal ODER Ctrl+C) die zuvor gestoppten Services wieder
# starten — so kehrt der Hintergrund-Betrieb nach einem manuellen Run zurück.
restart_services() {
    local u
    (( ${#STOPPED_UNITS[@]} == 0 )) && return
    for u in "${STOPPED_UNITS[@]}"; do
        echo "↻ starte Service wieder: $u"
        systemctl --user start "$u"
    done
}
trap restart_services EXIT

# ── Geräteauswahl: ohne Flag Schnellstart (-a -d), --menu überspringt das ────
# Wichtig: -a ALLEIN öffnet in einem Terminal (TTY) das interaktive
# Geräteauswahl-Menü und blockiert bei input() — der Keyboard-Listener startet
# dann nie, Alt+Alt bleibt wirkungslos. Deshalb den Default-Pfad nicht-interaktiv
# machen (-a -d = ein Default-Gerät für Input+Output, kein Menü; identisch zum
# Auto-Restart-Verhalten der run_*.sh). Wer bewusst wählen will: --menu.
# Ausnahme duplex: nutzt parec-Quellen (Mikro + Speaker-Monitor) statt der
# sounddevice-Geräteauswahl → kein -a, Argumente unverändert durchreichen.
if [[ "$MODE" != "duplex" ]]; then
    if [[ $# -eq 0 ]]; then
        set -- -a -d
    elif [[ "${1:-}" == "--menu" ]]; then
        shift
    fi
fi

echo "→ Modus: $MODE  ($SCRIPT)"
# Kein exec mehr: der manuelle Run läuft als Kind-Prozess, damit nach seinem
# Ende (auch Ctrl+C) der EXIT-Trap greift und die Services wieder hochfährt.
"$REPO/$SCRIPT" "$@"
