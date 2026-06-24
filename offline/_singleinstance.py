"""
Single-instance guard für die Transcription-Tools.

Warum: Alle Modi überwachen die Tastatur (Alt+Alt) und tippen Text an der
Cursor-Position. Laufen zwei Instanzen gleichzeitig (z. B. der systemd-Service
UND ein manuell gestartetes ./run_*.sh), erkennen BEIDE den Doppeltipp,
transkribieren dieselbe Audio und tippen beide am Cursor → der getippte Text
erscheint doppelt/vielfach, obwohl jedes einzelne Logfile sauber ist.

Diese Sperre stellt sicher, dass systemweit nur EINE Transcription-Instanz
gleichzeitig läuft. Der Lock wird per fcntl.flock auf einer festen Datei
gehalten; der File-Deskriptor bleibt für die gesamte Prozesslaufzeit offen.
Beim Prozess-Ende (auch Crash/kill) gibt das OS den flock automatisch frei.
"""

import os
import sys
import fcntl

# Ein gemeinsamer Lock über ALLE Modi — nur einer darf am Cursor tippen.
_LOCK_PATH = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
    f"desktop_transcription.{os.getuid()}.lock",
)

# Modulglobal: hält den fd offen, solange der Prozess lebt (sonst greift der GC
# und der Lock würde vorzeitig freigegeben).
_lock_fd = None


def acquire_or_exit():
    """Holt den globalen Single-Instance-Lock. Schlägt das fehl, läuft bereits
    eine andere Transcription-Instanz → klare Meldung und sauberer Exit."""
    global _lock_fd
    # "a+" statt "w": kein Truncate beim Öffnen — eine zweite Instanz, die den
    # Lock NICHT bekommt, darf die PID des Halters nicht versehentlich löschen.
    _lock_fd = open(_LOCK_PATH, "a+")
    try:
        fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            with open(_LOCK_PATH) as f:
                other = f.read().strip() or "?"
        except OSError:
            other = "?"
        msg = (
            "⚠️  Es läuft bereits eine Transcription-Instanz "
            f"(PID {other}).\n"
            "    Zwei Instanzen würden beide tippen → doppelter Text.\n"
            "    Laufenden Service stoppen mit:  transcription-stop\n"
            "    (oder den anderen Prozess beenden), dann erneut starten."
        )
        print(msg, file=sys.stderr)
        sys.exit(0)
    # PID hineinschreiben, damit eine zweite Instanz melden kann, wer hält.
    _lock_fd.seek(0)
    _lock_fd.truncate()
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
