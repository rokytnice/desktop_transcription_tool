#!/bin/bash



# Ermittle das Verzeichnis, in dem das Script liegt
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "$SCRIPT_DIR"
cd "$SCRIPT_DIR"

# Aktiviere das virtuelle Environment
if [ ! -d ".venv" ]; then
  echo "Virtual environment not found! Creating one..."
  python3 -m venv .venv
fi

source .venv/bin/activate

pip list

if [ -z "$DISPLAY" ]; then
    echo "Fehler: Keine grafische Umgebung erkannt (DISPLAY ist nicht gesetzt)."
    echo "Bitte führe das Skript in einer Desktop-Session aus!"
    exit 1
fi

# Prüfe, ob Zugriff auf den X-Server möglich ist
if ! xset q >/dev/null 2>&1; then
    echo "Fehler: Zugriff auf den X-Server nicht möglich. Eventuell fehlt die Berechtigung."
    echo "Starte das Skript in einer grafischen Desktop-Session und als der eingeloggte Desktop-User."
    echo "starte: xhost +SI:localuser:$USER"
    xhost +SI:localuser:$USER
    exit 1
fi

echo "Running the script..."
python $SCRIPT_DIR/transcription_offline.py




echo "Script finished."




# Optional: deactivate (nicht zwingend notwendig in Scripts)
deactivate 2>/dev/null || true
