# Verwaiste MANUELLE Läufe beenden — die halten sonst den Single-Instance-Lock
# und der neue Start steigt sofort wieder aus. Ein manueller Start heißt:
# DIESE Instanz soll tippen. (meeting/duplex haben eigene Locks und tippen
# nicht am Cursor — die bleiben unangetastet.)
TYPER_PATTERN='transcription_(offline|streaming|faster_streaming|claude)\.py'
OLD_PIDS=$(pgrep -f "$TYPER_PATTERN")
if [[ -n "$OLD_PIDS" ]]; then
    for pid in $OLD_PIDS; do
        echo "→ beende alte Instanz: PID $pid ($(ps -o args= -p "$pid" 2>/dev/null | awk '{print $NF, $(NF-1)}' | head -c 60))"
        kill -INT "$pid" 2>/dev/null || true
    done
    for _ in 1 2 3 4 5; do
        pgrep -f "$TYPER_PATTERN" >/dev/null || break
        sleep 1
    done
    if pgrep -f "$TYPER_PATTERN" >/dev/null; then
        echo "→ Instanz reagiert nicht — hartes Beenden (SIGKILL)"
        pkill -9 -f "$TYPER_PATTERN" 2>/dev/null || true
        sleep 1
    fi
fi
