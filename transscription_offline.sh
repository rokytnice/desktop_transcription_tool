sudo apt update && sudo apt installsudo apt update && sudo apt install xdotool xdotool#!/bin/bash

# Wechselt in das Verzeichnis, in dem das Bash-Skript liegt
# Dies stellt sicher, dass relative Pfade korrekt funktionieren, egal von wo aus das Skript aufgerufen wird.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Definiere den Pfad zum Python-Skript und zum virtuellen Environment
PYTHON_SCRIPT="transcription_listener_offline.py"
VENV_DIR=".venv" # Standardname für virtuelle Umgebungen

# --- Überprüfungen ---

# 1. Prüfen, ob das Python-Skript existiert
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Fehler: Python-Skript '$PYTHON_SCRIPT' nicht im Verzeichnis $SCRIPT_DIR gefunden."
    exit 1
fi

# 2. Prüfen, ob das virtuelle Environment-Verzeichnis existiert
if [ ! -d "$VENV_DIR" ]; then
    echo "Fehler: Virtuelles Environment '$VENV_DIR' nicht im Verzeichnis $SCRIPT_DIR gefunden."
    echo "Bitte erstelle es mit: python3 -m venv $VENV_DIR"
    echo "Und installiere die Abhängigkeiten mit: source $VENV_DIR/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 3. Prüfen, ob das Aktivierungsskript für das venv existiert
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Fehler: Aktivierungsskript '$VENV_DIR/bin/activate' nicht gefunden."
    echo "Das virtuelle Environment scheint unvollständig zu sein."
    exit 1
fi

# 4. Prüfen, ob 'xdotool' installiert ist (wird vom Python-Skript benötigt)
if ! command -v xdotool &> /dev/null; then
    echo "Fehler: Das Programm 'xdotool' wird benötigt, wurde aber nicht gefunden."
    echo "Bitte installiere es mit deinem Paketmanager (z.B. 'sudo apt install xdotool' oder 'sudo dnf install xdotool')."
    exit 1
fi

# --- Ausführung ---

echo "Aktiviere virtuelles Environment: $VENV_DIR"
source "$VENV_DIR/bin/activate"

# Überprüfen, ob die Aktivierung erfolgreich war (optional, aber gut)
# Prüft, ob der Python-Interpreter jetzt der aus dem venv ist
EXPECTED_PYTHON="$SCRIPT_DIR/$VENV_DIR/bin/python3"
CURRENT_PYTHON=$(which python3)
# Beachte: 'which python3' könnte je nach Systemkonfiguration variieren.
# Eine robustere Prüfung ist oft nicht trivial in Bash. Wir gehen davon aus, dass 'source' funktioniert hat.
# if [ "$CURRENT_PYTHON" != "$EXPECTED_PYTHON" ]; then
#     echo "Warnung: Konnte nicht sicherstellen, dass das venv korrekt aktiviert wurde."
# fi


echo "Starte das Transkriptions-Listener-Skript: $PYTHON_SCRIPT"
echo "Drücke Strg+C, um das Skript (und diesen Launcher) zu beenden."

# Führe das Python-Skript aus
python3 "$PYTHON_SCRIPT"

# Das Skript wird hier warten, bis das Python-Skript beendet wird (z.B. durch Strg+C im Listener oder einen Fehler)

echo "Transkriptions-Listener beendet."

# Deaktiviere das virtuelle Environment (optional, geschieht automatisch beim Beenden des Skripts)
# deactivate

exit 0