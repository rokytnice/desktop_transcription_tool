#!/bin/bash
#
# setup-service.sh — Transcription-Service einrichten (Autostart bei Rechnerstart)
#
# VERWENDUNG
#   ./setup-service.sh [MODUS] [OPTIONEN]
#
# MODUS
#   offline            Klassisch: aufnehmen → stoppen → am Cursor tippen  [Standard]
#   streaming          VAD-Streaming an Sprechpausen (openai-whisper)
#   faster-streaming   Wortweises Live-Streaming (faster-whisper)
#   claude             Sprache → Claude Code → Antwort im Fenster
#
# OPTIONEN
#   --model NAME   Whisper-Modell (tiny|base|small|medium|large)  (Standard: small)
#   --device IDX   Audio-Gerät-Index (Input+Output)  (Standard: -a / Auto)
#   --no-start     Service nur einrichten + aktivieren, nicht sofort starten
#   -h, --help     Diese Hilfe anzeigen
#
# BESCHREIBUNG
#   Erzeugt eine systemd-User-Unit (transcription.service) für den gewählten
#   Modus, aktiviert sie für Autostart und startet sie. Der Service läuft als
#   User-Service und wird über `loginctl enable-linger` so eingerichtet, dass
#   der User-Manager bereits BEI RECHNERSTART hochfährt; die Unit ist an
#   graphical-session.target gebunden und startet, sobald die Wayland-Sitzung
#   bereit ist (Tippen an der Cursor-Position braucht eine aktive Sitzung).
#
#   Pfade (Repo, venv, Runtime-Dir, Wayland-Display) werden automatisch
#   erkannt — nichts ist hartkodiert. Ein eventuell vorhandener alter
#   transcription-offline.service wird sauber durch transcription.service
#   ersetzt, damit nicht zwei Services gleichzeitig tippen.
#
# NACH DER EINRICHTUNG (global ausführbar)
#   transcription-restart   Service neu starten
#   transcription-start     Service starten
#   transcription-stop      Service stoppen
#   transcription-status    Status anzeigen
#   transcription-log       Live-Log (journalctl -f)
#
# BEISPIELE
#   ./setup-service.sh                          Offline-Modus (Standard), Modell small
#   ./setup-service.sh streaming                VAD-Streaming an Sprechpausen
#   ./setup-service.sh faster-streaming --model tiny   geringste Latenz
#   ./setup-service.sh offline --device 7       festes Audio-Gerät 7

set -euo pipefail

# ── Hilfe ───────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

# ── Argumente parsen ────────────────────────────────────────────────────────
MODE="offline"
WHISPER_MODEL="small"
DEVICE=""
DO_START=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        faster-streaming|streaming|offline|claude) MODE="$1"; shift ;;
        --model) WHISPER_MODEL="$2"; shift 2 ;;
        --device) DEVICE="$2"; shift 2 ;;
        --no-start) DO_START=0; shift ;;
        *) echo "Unbekannte Option: $1 (./setup-service.sh --help)"; exit 1 ;;
    esac
done

# ── Modus → Python-Script ───────────────────────────────────────────────────
case "$MODE" in
    offline)          PY_SCRIPT="transcription_offline.py";          DESC="Offline (aufnehmen → stoppen → Clipboard)" ;;
    streaming)        PY_SCRIPT="transcription_streaming.py";        DESC="VAD-Streaming (openai-whisper)" ;;
    faster-streaming) PY_SCRIPT="transcription_faster_streaming.py"; DESC="Live-Streaming (faster-whisper)" ;;
    claude)           PY_SCRIPT="transcription_claude.py";           DESC="Sprache → Claude Code → Fenster" ;;
esac

# ── Pfade automatisch erkennen ──────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE_DIR="$REPO_DIR/offline"
VENV_PY="$OFFLINE_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
    echo "✗ venv nicht gefunden: $VENV_PY"
    echo "  Zuerst ./install.sh ausführen."
    exit 1
fi
if [[ ! -f "$OFFLINE_DIR/$PY_SCRIPT" ]]; then
    echo "✗ Script nicht gefunden: $OFFLINE_DIR/$PY_SCRIPT"
    exit 1
fi

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
WL_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
X_DISPLAY="${DISPLAY:-:0}"   # XWayland — wird vom claude-Modus (Tk-Fenster) gebraucht

# Audio-Gerät: festes Gerät → -a überschreiben, sonst Auto (-a = ein Gerät In+Out)
DEVICE_ENV=""
if [[ -n "$DEVICE" ]]; then
    DEVICE_ENV="Environment=\"AUDIO_DEVICE=$DEVICE\"
Environment=\"AUDIO_OUTPUT_DEVICE=$DEVICE\""
fi

SERVICE="transcription-$MODE.service"
USER_UNIT_DIR="$HOME/.config/systemd/user"
SERVICE_DST="$USER_UNIT_DIR/$SERVICE"

echo "╔════════════════════════════════════════════════════╗"
echo "║  Transcription-Service einrichten                  ║"
echo "╚════════════════════════════════════════════════════╝"
echo "  Modus       : $MODE  ($DESC)"
echo "  Service     : $SERVICE"
echo "  Modell      : $WHISPER_MODEL"
echo "  Audio-Gerät : ${DEVICE:-Auto (-a)}"
echo "  Repo        : $REPO_DIR"
echo "  Runtime-Dir : $RUNTIME_DIR"
echo "  Wayland     : $WL_DISPLAY"
echo ""

# ── Linger aktivieren: User-Manager startet bei Rechnerstart ────────────────
if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
    echo "→ Linger aktivieren (User-Service-Start bei Boot)..."
    loginctl enable-linger "$USER"
fi

# ── Andere/alte Transcription-Units ablösen (nur einer darf tippen) ─────────
for other in transcription.service transcription-offline.service \
             transcription-streaming.service transcription-faster-streaming.service \
             transcription-claude.service; do
    [[ "$other" == "$SERVICE" ]] && continue
    if [[ -f "$USER_UNIT_DIR/$other" ]] || systemctl --user is-enabled "$other" &>/dev/null; then
        echo "→ $other ablösen..."
        systemctl --user disable --now "$other" 2>/dev/null || true
        rm -f "$USER_UNIT_DIR/$other"
    fi
done

# ── Unit erzeugen ───────────────────────────────────────────────────────────
echo "→ $SERVICE schreiben..."
mkdir -p "$USER_UNIT_DIR"
cat > "$SERVICE_DST" << UNIT
[Unit]
Description=Desktop Transcription Tool ($MODE)
Documentation=https://github.com/rokytnice/desktop_transcription_tool
After=graphical-session.target pipewire.service pipewire-pulse.service
Wants=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
# Höhere Priorität: mehr CPU-/IO-Anteil unter Last (cgroup-Gewichte, brauchen
# KEIN root — Default ist 100, hier deutlich höher, damit die Whisper-
# Transkription auch bei ausgelastetem System flüssig bleibt).
CPUWeight=900
IOWeight=900
# Negatives Nice (echte Scheduler-Priorität) ist für User-Services standardmäßig
# gesperrt (RLIMIT_NICE=0). Aktivieren mit:
#   echo '$USER  -  nice  -10' | sudo tee /etc/security/limits.d/transcription-nice.conf
# danach neu einloggen und in dieser Unit `Nice=-10` ergänzen.
Environment="WHISPER_MODEL=$WHISPER_MODEL"
Environment="XDG_RUNTIME_DIR=$RUNTIME_DIR"
Environment="WAYLAND_DISPLAY=$WL_DISPLAY"
Environment="DISPLAY=$X_DISPLAY"
$DEVICE_ENV
WorkingDirectory=$OFFLINE_DIR
ExecStart=$VENV_PY $OFFLINE_DIR/$PY_SCRIPT -a
# on-failure statt always: sauberer Exit 0 (z. B. Single-Instance-Lock belegt,
# weil eine manuelle Instanz läuft) löst KEINEN Neustart aus — sonst hämmert der
# Service alle 10s neu. Device-lost (Exit 75) und Crashes sind non-zero → Restart.
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target default.target
UNIT

# ── Globale Kommandos ───────────────────────────────────────────────────────
echo "→ Globale Kommandos installieren (~/.local/bin)..."
mkdir -p "$HOME/.local/bin"

_gen_cmd() {  # name, systemctl-args...
    local name="$1"; shift
    cat > "$HOME/.local/bin/$name" << CMD
#!/bin/bash
systemctl --user $* $SERVICE
CMD
    chmod +x "$HOME/.local/bin/$name"
}
_gen_cmd transcription-restart restart
_gen_cmd transcription-start   start
_gen_cmd transcription-stop    stop
cat > "$HOME/.local/bin/transcription-status" << CMD
#!/bin/bash
systemctl --user status $SERVICE --no-pager
CMD
cat > "$HOME/.local/bin/transcription-log" << CMD
#!/bin/bash
journalctl --user -u $SERVICE -f
CMD
chmod +x "$HOME/.local/bin/transcription-status" "$HOME/.local/bin/transcription-log"

# ── `transcription` — ein Kommando für alle Modi (manueller Start im Terminal) ─
# Quoted-Heredoc (nichts expandiert), Repo-Pfad per Platzhalter __REPO__ ersetzt.
cat > "$HOME/.local/bin/transcription" << 'LAUNCHER'
#!/bin/bash
#
# transcription — Desktop Transcription Tool starten (ein Kommando, alle Modi)
#
# MODUS
#   offline    Aufnehmen → stoppen → Text wird am Cursor getippt   (nicht-streaming)
#   stream     Wortweise live beim Sprechen (faster-whisper)
#   vad        Streaming an jeder Sprechpause (Voice Activity Detection)  [Standard]
#   claude     Sprache → Claude Code → Antwort im Fenster
#
# OPTIONEN (werden an das run_*.sh durchgereicht)
#   (kein Flag)   -a: ein Gerät für Input+Output (z.B. Jabra)
#   --menu        interaktive Geräteauswahl (kein -a)
#   -d            Schnellstart mit Default-Geräten, kein Menü
#   -h, --help    Diese Hilfe
#
# BEISPIELE
#   transcription            vad-Modus (Standard)
#   transcription offline    Offline-Modus
#   transcription stream     Wortweises Live-Streaming

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    sed -n '/^#$/,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
fi

REPO="__REPO__"

MODE="vad"
case "$1" in
    offline|stream|vad|claude) MODE="$1"; shift ;;
esac
case "$MODE" in
    offline) SCRIPT="run_offline.sh" ;;
    stream)  SCRIPT="run_faster_streaming.sh" ;;
    vad)     SCRIPT="run_streaming.sh" ;;
    claude)  SCRIPT="run_claude.sh" ;;
esac

# Laufenden Transcription-Service stoppen (gegen doppeltes Tippen).
# Gestoppte Units merken → beim Beenden wieder starten (sonst bleibt der
# Autostart-Service nach einem manuellen `transcription`-Lauf dauerhaft aus).
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

# Beim Beenden (Ctrl+C, normaler Exit, Kill) die gestoppten Services wieder
# hochfahren. Kein `exec`, damit der Trap überhaupt greifen kann.
restore_services() {
    trap - EXIT INT TERM   # nur EINMAL laufen (INT feuert sonst zusätzlich EXIT)
    [[ ${#STOPPED_UNITS[@]} -eq 0 ]] && return 0
    # Kurz warten: bei Ctrl+C kann das Python-Kind den Single-Instance-Lock noch
    # halten — der Service würde sonst sofort mit Exit 0 wieder aussteigen.
    sleep 1
    for name in "${STOPPED_UNITS[@]}"; do
        echo "→ starte Service wieder: $name"
        systemctl --user start "$name" 2>/dev/null || true
    done
}
trap restore_services EXIT INT TERM

# Geräte-Default: ohne Argumente -a; --menu = interaktiv (kein -a)
if [[ $# -eq 0 ]]; then
    set -- -a
elif [[ "$1" == "--menu" ]]; then
    shift
fi

echo "→ Modus: $MODE  ($SCRIPT)"
"$REPO/$SCRIPT" "$@"
LAUNCHER
sed -i "s|__REPO__|$REPO_DIR|" "$HOME/.local/bin/transcription"
chmod +x "$HOME/.local/bin/transcription"

if ! grep -q 'local/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi

# ── Aktivieren + starten ────────────────────────────────────────────────────
echo "→ Service aktivieren..."
systemctl --user daemon-reload
systemctl --user enable "$SERVICE" >/dev/null 2>&1 || true

if [[ "$DO_START" -eq 1 ]]; then
    echo "→ Service starten..."
    systemctl --user restart "$SERVICE"
fi

echo ""
echo "✓ Fertig — $SERVICE ($MODE) eingerichtet und für Autostart aktiviert."
echo ""
echo "  Steuerung (überall):"
echo "    transcription-status    Status"
echo "    transcription-restart   Neu starten"
echo "    transcription-stop      Stoppen"
echo "    transcription-log       Live-Log"
echo ""
if [[ "$DO_START" -eq 1 ]]; then
    systemctl --user status "$SERVICE" --no-pager || true
fi
