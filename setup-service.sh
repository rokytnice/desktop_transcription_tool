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
#   --model NAME        Whisper-Modell (tiny|base|small|medium|large)  (Standard: small)
#   --device IDX        Audio-Gerät-Index (Input+Output)  (Standard: -a / Auto)
#   --min-silence S     Pause in s, die eine Phrase beendet     (Standard: 0.7)
#   --silence-rms X     Stille-Schwelle (RMS)                   (Standard: 0.010)
#   --max-phrase S      Zwangs-Flush langer Phrasen in s        (Standard: 15)
#   --idle-timeout S    Leerlauf bis Auto-Stop in s, 0 = aus    (Standard: 15)
#   --no-start          Service nur einrichten + aktivieren, nicht sofort starten
#   -h, --help          Diese Hilfe anzeigen
#
#   Die Pausen-Optionen gelten für streaming/faster-streaming und landen als
#   STREAM_*-Umgebungsvariablen in der Unit.
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
# base statt small: deutlich weniger Rechenlast pro Inferenz-Lauf, damit unter
# System-Last mehr Spielraum für den Audio-Callback-Thread bleibt (siehe
# _wiki/troubleshooting.md, "Transkriptionsqualität schlecht bei hoher Last").
WHISPER_MODEL="base"
DEVICE=""
DO_START=1
# VAD-/Pausen-Tuning (nur für streaming/faster-streaming relevant, leere Werte
# = Defaults des Python-Skripts). Sekunden bzw. RMS-Schwelle.
MIN_SILENCE=""      # Pause, die eine Phrase beendet (Default 0.7s)
SILENCE_RMS=""      # Stille-Schwelle (Default 0.010)
MAX_PHRASE=""       # Zwangs-Flush langer Phrasen (Default 15s)
IDLE_TIMEOUT=""     # Leerlauf bis Auto-Stop, 0 = aus (Default 15s)

while [[ $# -gt 0 ]]; do
    case "$1" in
        faster-streaming|streaming|offline|claude) MODE="$1"; shift ;;
        --model) WHISPER_MODEL="$2"; shift 2 ;;
        --device) DEVICE="$2"; shift 2 ;;
        --min-silence) MIN_SILENCE="$2"; shift 2 ;;
        --silence-rms) SILENCE_RMS="$2"; shift 2 ;;
        --max-phrase) MAX_PHRASE="$2"; shift 2 ;;
        --idle-timeout) IDLE_TIMEOUT="$2"; shift 2 ;;
        --no-start) DO_START=0; shift ;;
        *) echo "Unbekannte Option: $1 (./setup-service.sh --help)"; exit 1 ;;
    esac
done

# VAD-Env-Zeilen für die Unit zusammenbauen (nur gesetzte Werte)
VAD_ENV=""
[[ -n "$MIN_SILENCE" ]]  && VAD_ENV+="Environment=\"STREAM_MIN_SILENCE=$MIN_SILENCE\""$'\n'
[[ -n "$SILENCE_RMS" ]]  && VAD_ENV+="Environment=\"STREAM_SILENCE_RMS=$SILENCE_RMS\""$'\n'
[[ -n "$MAX_PHRASE" ]]   && VAD_ENV+="Environment=\"STREAM_MAX_PHRASE=$MAX_PHRASE\""$'\n'
[[ -n "$IDLE_TIMEOUT" ]] && VAD_ENV+="Environment=\"STREAM_IDLE_TIMEOUT=$IDLE_TIMEOUT\""$'\n'

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
# Leichter Vorrang statt Default (100/0): Whisper-Inferenz ist inzwischen auf
# max. 4 Threads gedeckelt (torch.set_num_threads/cpu_threads in den
# transcription_*.py), belegt also nur einen Teil der Kerne. Ein früherer
# Versuch mit unbegrenzten Threads + hoher Priorität hat den ganzen Desktop
# ausgebremst — das war die Kombination aus "alle Kerne" + "bevorzugt", nicht
# die Priorität allein. Mit dem Thread-Cap ist ein moderater Bump risikoarm:
# betrifft höchstens 4 von 20 Kernen, die übrigen bleiben für den Rest des
# Desktops uneingeschränkt verfügbar. Bei erneuten Aussetzern unter Last
# (siehe "Audio status:" im Log) auf 100/0 zurücksetzen.
CPUWeight=150
IOWeight=100
Nice=-5
Environment="WHISPER_MODEL=$WHISPER_MODEL"
Environment="XDG_RUNTIME_DIR=$RUNTIME_DIR"
Environment="WAYLAND_DISPLAY=$WL_DISPLAY"
Environment="DISPLAY=$X_DISPLAY"
$VAD_ENV$DEVICE_ENV
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

# ── `transcription-mode` — Service-Modus umschalten (offline ⇄ vad ⇄ …) ─────
cat > "$HOME/.local/bin/transcription-mode" << MODESWITCH
#!/bin/bash
#
# transcription-mode — Service-Modus umschalten
#
#   transcription-mode              aktuellen Modus anzeigen
#   transcription-mode offline      Aufnehmen → stoppen → tippen
#   transcription-mode vad          Streaming an Sprechpausen (Standard-Streaming)
#   transcription-mode stream       Wortweises Live-Streaming (faster-whisper)
#   transcription-mode claude       Sprache → Claude Code
#   transcription-mode meeting      Meeting-Modus starten (manuell, kein Service)
#
# Weitere Optionen (z. B. --min-silence 1.0) werden an setup-service.sh durchgereicht.
REPO="$REPO_DIR"
case "\${1:-}" in
    "" )
        cur=\$(systemctl --user list-units 'transcription-*' --plain --no-legend | awk '{print \$1}' | head -1)
        echo "Aktiver Modus: \${cur:-keiner}"
        echo "Umschalten: transcription-mode offline|vad|stream|claude"
        echo "Meeting (manuell): transcription-mode meeting"
        ;;
    offline)         exec "\$REPO/setup-service.sh" offline          "\${@:2}" ;;
    vad|streaming)   exec "\$REPO/setup-service.sh" streaming        "\${@:2}" ;;
    stream|faster)   exec "\$REPO/setup-service.sh" faster-streaming "\${@:2}" ;;
    claude)          exec "\$REPO/setup-service.sh" claude           "\${@:2}" ;;
    meeting)         exec "\$HOME/.local/bin/transcription" meeting  "\${@:2}" ;;
    *) echo "Unbekannter Modus: \$1 (offline|vad|stream|claude|meeting)"; exit 1 ;;
esac
MODESWITCH
chmod +x "$HOME/.local/bin/transcription-mode"

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
#   meeting    Mikro+Speaker mithören → Transkript + Live-Stichpunkte + Protokoll
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
    offline|stream|vad|claude|meeting) MODE="$1"; shift ;;
esac
case "$MODE" in
    offline) SCRIPT="run_offline.sh" ;;
    stream)  SCRIPT="run_faster_streaming.sh" ;;
    vad)     SCRIPT="run_streaming.sh" ;;
    claude)  SCRIPT="run_claude.sh" ;;
    meeting) SCRIPT="run_meeting.sh" ;;
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
    # `|| true` ist Pflicht: is-active liefert bei inaktiver Unit Exit 3, und
    # eine Zuweisung erbt den Status der Command-Substitution — unter `set -e`
    # bräche der Launcher hier stumm ab, sobald kein Service läuft.
    state="$(systemctl --user is-active "$name" 2>/dev/null || true)"
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

# Verwaiste MANUELLE Läufe beenden — die halten sonst den Single-Instance-Lock
# und der neue Start steigt sofort wieder aus. Ein manueller Start heißt:
# DIESE Instanz soll tippen. (meeting/duplex haben eigene Locks und tippen
# nicht am Cursor — die bleiben unangetastet.)
TYPER_PATTERN='bin/python[0-9.]* .*transcription_(offline|streaming|faster_streaming|claude)\.py'
# pgrep gibt Exit 1 zurück, wenn nichts läuft — unter `set -e` sonst Abbruch.
OLD_PIDS=$(pgrep -f "$TYPER_PATTERN" || true)
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

# Geräte-Default: ohne Argumente -a; --menu = interaktiv (kein -a).
# meeting nutzt parec (PipeWire-Quellen direkt) — keine Geräte-Flags.
if [[ "$MODE" != "meeting" ]]; then
    if [[ $# -eq 0 ]]; then
        set -- -a
    elif [[ "$1" == "--menu" ]]; then
        shift
    fi
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
