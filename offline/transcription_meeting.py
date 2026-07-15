#!/usr/bin/env python3
"""
Meeting-Modus — Mikro + Speaker mithören → Live-Erläuterungen + Protokoll.

Eigenständige Funktion (getrennt vom VAD-Streaming und vom Duplex-Modus):

  • Hört GLEICHZEITIG Mikrofon (🎤 Du) und Lautsprecher-Monitor (🔊 Gegenüber)
    über `parec` mit und transkribiert an Sprechpausen (VAD).
  • Jeder abgeschlossene Turn wird mit Zeitstempel + Sprecher in ein
    persistentes Markdown-Transkript geschrieben.
  • Bei jeder Sprechpause geht der Turn-Text an `claude -p` mit dem Auftrag,
    den Inhalt KURZ UND KNAPP als Stichpunkte zu erläutern — oder eine
    gestellte Frage direkt zu beantworten. Die Stichpunkte erscheinen live
    im Fenster (nicht am Cursor, kein Tippen).
  • Beim Beenden (Button oder Fenster schließen) erzeugt Claude aus dem
    Transkript ein strukturiertes Protokoll (Themen, Entscheidungen,
    Action Items, Zusammenfassung).

AUSGABE
    ~/Dokumente/meetings/YYYY-MM-DD_HHMM_transkript.md   (live, fortlaufend)
    ~/Dokumente/meetings/YYYY-MM-DD_HHMM_protokoll.md    (beim Beenden)

VERWENDUNG
    ./run_meeting.sh [--no-mic | --no-speaker]

UMGEBUNGSVARIABLEN
    WHISPER_MODEL          tiny|base|small|medium|large   (Standard: small)
    STREAM_SILENCE_RMS     Stille-Schwelle                (Standard: 0.010)
    MEETING_TURN_SILENCE   Pause → Turn abschließen, s    (Standard: 1.2)
    MEETING_MIN_TURN       Mindestlänge Turn, s           (Standard: 0.4)
    MEETING_MAX_TURN       Turn-Notbremse (Monolog), s    (Standard: 30.0)
    MEETING_DIR            Ausgabeverzeichnis             (Standard: ~/Dokumente/meetings)
    CLAUDE_MODEL           Modell für Claude              (optional, z. B. haiku)
    MIC_SOURCE             parec-Quelle Mikro             (Standard: @DEFAULT_SOURCE@)
    SPEAKER_SOURCE         parec-Quelle Monitor           (Standard: <default-sink>.monitor)

HINWEIS (Echo)
    Bei offenen Lautsprechern nimmt das Mikro auch den Speaker-Ton auf →
    doppelte Turns. Kopfhörer nutzen oder eine Quelle abschalten.
"""

import os
import sys
import queue
import signal
import threading
import subprocess
import uuid
from datetime import datetime

import numpy as np

# Whisper-Modell, VAD-Konstanten und transcribe_chunk aus dem vad-Modul teilen.
import transcription_streaming as base

import tkinter as tk
from tkinter import scrolledtext
import tkinter.font as tkfont


# ── Konfiguration ─────────────────────────────────────────────────────────────
def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


TURN_SILENCE = _envf("MEETING_TURN_SILENCE", 1.2)   # s Pause → Turn fertig
MIN_TURN = _envf("MEETING_MIN_TURN", 0.4)           # s Mindestlänge
MAX_TURN = _envf("MEETING_MAX_TURN", 30.0)          # s Notbremse Monolog

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
SESSION_ID = str(uuid.uuid4())   # eine Session pro Meeting → Kontext bleibt
_first_turn = True
_claude_lock = threading.Lock()

LIVE_PROMPT = (
    "Du bist stiller Meeting-Assistent. Du bekommst nacheinander Gesprächs-"
    "Ausschnitte eines laufenden Meetings ([🎤 Du] = ich, [🔊 Gegenüber] = "
    "andere Teilnehmer). Antworte zu JEDEM Ausschnitt KURZ UND KNAPP als "
    "Stichpunkte (max. 3–4 Punkte, je eine Zeile): erläutere den Inhalt bzw. "
    "erkläre erwähnte Begriffe/Zusammenhänge — und wenn eine Frage gestellt "
    "wird, beantworte sie direkt. Kein Fließtext, keine Einleitung, keine "
    "Rückfragen, kein Markdown-Header. Wenn es nichts Erwähnenswertes gibt, "
    "antworte nur mit „–“."
)

# Thread-sichere Brücke Worker → GUI.
gui_queue: "queue.Queue[tuple]" = queue.Queue()
# Fertige Turns (timestamp, label, text) → Transkript + Claude, seriell.
turn_queue: "queue.Queue[tuple]" = queue.Queue()

_stop = threading.Event()


# ── Ausgabe-Dateien ───────────────────────────────────────────────────────────
def _meetings_dir() -> str:
    d = os.environ.get("MEETING_DIR")
    if not d:
        try:
            docs = subprocess.run(
                ["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=3
            ).stdout.strip()
        except Exception:
            docs = ""
        if not docs or docs == os.path.expanduser("~"):
            docs = os.path.expanduser("~/Dokumente")
        d = os.path.join(docs, "meetings")
    os.makedirs(d, exist_ok=True)
    return d


MEETING_START = datetime.now()
_STAMP = MEETING_START.strftime("%Y-%m-%d_%H%M")
MEETINGS_DIR = _meetings_dir()
TRANSCRIPT_PATH = os.path.join(MEETINGS_DIR, f"{_STAMP}_transkript.md")
PROTOCOL_PATH = os.path.join(MEETINGS_DIR, f"{_STAMP}_protokoll.md")

_transcript_lock = threading.Lock()


def _init_transcript():
    with _transcript_lock, open(TRANSCRIPT_PATH, "w") as f:
        f.write(
            f"# Meeting-Transkript — {MEETING_START.strftime('%d.%m.%Y %H:%M')}\n\n"
            "Sprecher: 🎤 Du (Mikrofon) · 🔊 Gegenüber (Lautsprecher)\n\n"
        )


def _append_transcript(ts: str, label: str, text: str):
    with _transcript_lock, open(TRANSCRIPT_PATH, "a") as f:
        f.write(f"- **{ts} · {label}:** {text}\n")


# ── parec-Quellen ermitteln ──────────────────────────────────────────────────
def _pactl(*args) -> str:
    try:
        return subprocess.run(
            ["pactl", *args], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ""


def default_mic_source() -> str:
    return os.environ.get("MIC_SOURCE") or _pactl("get-default-source") or "@DEFAULT_SOURCE@"


def default_speaker_source() -> str:
    if os.environ.get("SPEAKER_SOURCE"):
        return os.environ["SPEAKER_SOURCE"]
    sink = _pactl("get-default-sink")
    return f"{sink}.monitor" if sink else "@DEFAULT_MONITOR@"


# ── VAD-Segmentierer je Audioquelle (via parec) ──────────────────────────────
class VADSource(threading.Thread):
    """Liest eine PulseAudio/PipeWire-Quelle über `parec` als 16 kHz float32-Mono
    und schneidet an Sprechpausen ganze Turns, die als (timestamp, label, text)
    in die turn-Pipeline gehen (→ Transkript + Claude-Erläuterung)."""

    def __init__(self, label: str, source: str):
        super().__init__(daemon=True)
        self.label = label
        self.source = source
        self.block_bytes = base.BLOCKSIZE * 4          # float32 = 4 Byte
        self.block_dur = base.BLOCKSIZE / base.samplerate

    def _spawn(self):
        cmd = [
            "parec",
            "--format=float32le",
            f"--rate={base.samplerate}",
            "--channels=1",
            f"--device={self.source}",
            "--latency-msec=100",
            "--client-name=meeting",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _flush(self, seg, seg_samples, started_at):
        if seg_samples < MIN_TURN * base.samplerate:
            return
        audio = np.concatenate(seg).astype(np.float32)
        text = base.transcribe_chunk(audio)
        if text and text.strip():
            turn_queue.put((started_at.strftime("%H:%M:%S"), self.label, text.strip()))

    def run(self):
        while not _stop.is_set():
            try:
                proc = self._spawn()
            except FileNotFoundError:
                gui_queue.put(("status", "✗ `parec` (pulseaudio-utils) nicht gefunden"))
                return
            seg, seg_samples = [], 0
            silence_run = 0.0
            in_turn = False
            started_at = None
            try:
                while not _stop.is_set():
                    data = proc.stdout.read(self.block_bytes)
                    if len(data) < self.block_bytes:
                        break  # Quelle verloren/EOF → neu verbinden
                    block = np.frombuffer(data, dtype=np.float32)
                    rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0

                    if rms >= base.SILENCE_RMS:
                        if not in_turn:
                            in_turn = True
                            started_at = datetime.now()
                        seg.append(block)
                        seg_samples += len(block)
                        silence_run = 0.0
                    elif in_turn:
                        seg.append(block)
                        seg_samples += len(block)
                        silence_run += self.block_dur
                        # Sprechpause → Turn abschließen.
                        if silence_run >= TURN_SILENCE:
                            self._flush(seg, seg_samples, started_at)
                            seg, seg_samples = [], 0
                            silence_run, in_turn = 0.0, False
                    # Notbremse: langer Monolog ohne Pause.
                    if seg_samples >= MAX_TURN * base.samplerate:
                        self._flush(seg, seg_samples, started_at)
                        seg, seg_samples = [], 0
                        silence_run, in_turn = 0.0, False
            finally:
                try:
                    proc.kill()
                except Exception:
                    pass
            if not _stop.is_set():
                base.logger.warning(f"[{self.label}] parec-Quelle beendet — neu verbinden…")
                _stop.wait(1.0)


# ── Claude: Live-Erläuterung (Stichpunkte) ───────────────────────────────────
def _run_claude(cmd_args, prompt, cwd=None, timeout=120):
    """Startet `claude -p` und liefert stdout (oder Fehlermeldung)."""
    cmd = ["claude", "-p", *cmd_args]
    if CLAUDE_MODEL:
        cmd += ["--model", CLAUDE_MODEL]
    cmd += [prompt]
    try:
        proc = subprocess.run(
            cmd, cwd=cwd or os.path.expanduser("~"),
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return "[Fehler: `claude` nicht im PATH]"
    except subprocess.TimeoutExpired:
        return "[Fehler: Claude-Timeout]"
    out = (proc.stdout or "").strip()
    if out:
        return out
    err = (proc.stderr or "").strip()
    return f"[keine Antwort] {err}" if err else "[keine Antwort]"


def explain_turn(label: str, text: str) -> str:
    global _first_turn
    with _claude_lock:
        if _first_turn:
            args = ["--session-id", SESSION_ID]
            prompt = f"{LIVE_PROMPT}\n\n[{label}] {text}"
            _first_turn = False
        else:
            args = ["--resume", SESSION_ID]
            prompt = f"[{label}] {text}"
        return _run_claude(args, prompt)


def turn_worker():
    """Nimmt fertige Turns aus der Pipeline: Transkript schreiben, im Fenster
    anzeigen, dann Claude-Erläuterung holen — seriell, damit die Session
    konsistent bleibt."""
    while not _stop.is_set():
        try:
            ts, label, text = turn_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        _append_transcript(ts, label, text)
        gui_queue.put(("turn", (ts, label, text)))
        gui_queue.put(("status", "🤔 Claude erläutert…"))
        answer = explain_turn(label, text)
        if answer.strip() not in ("–", "-", ""):
            gui_queue.put(("claude", answer))
        gui_queue.put(("status", "🎧 Meeting läuft — höre zu…"))


# ── Protokoll beim Beenden ────────────────────────────────────────────────────
PROTOCOL_PROMPT = """Du bekommst das Transkript eines Meetings (Markdown, mit \
Zeitstempeln; 🎤 Du = ich, 🔊 Gegenüber = andere Teilnehmer). Erstelle daraus \
ein strukturiertes Meeting-Protokoll auf Deutsch, als Markdown mit genau diesen \
Abschnitten:

# Meeting-Protokoll — {date}

## Zusammenfassung
(3–6 Sätze)

## Themen
(Stichpunkte je Thema)

## Entscheidungen
(nur tatsächlich getroffene Entscheidungen; sonst „keine“)

## Action Items
(als Checkliste `- [ ]`, mit Verantwortlichem falls erkennbar; sonst „keine“)

## Offene Fragen
(sonst „keine“)

Gib NUR das Protokoll aus, keinen weiteren Text.

--- TRANSKRIPT ---
{transcript}"""


def generate_protocol() -> str:
    """Erzeugt aus dem Transkript das Protokoll (eigener Claude-Aufruf ohne
    Session) und speichert es. Gibt den Pfad oder eine Fehlermeldung zurück."""
    try:
        with _transcript_lock, open(TRANSCRIPT_PATH) as f:
            transcript = f.read()
    except OSError as e:
        return f"[Fehler: Transkript nicht lesbar: {e}]"
    if transcript.count("\n- **") == 0:
        return "[kein Gesprächsinhalt — Protokoll übersprungen]"
    prompt = PROTOCOL_PROMPT.format(
        date=MEETING_START.strftime("%d.%m.%Y %H:%M"), transcript=transcript
    )
    out = _run_claude([], prompt, timeout=300)
    if out.startswith("["):
        return out
    with open(PROTOCOL_PATH, "w") as f:
        f.write(out.rstrip() + "\n")
    return PROTOCOL_PATH


# ── GUI ───────────────────────────────────────────────────────────────────────
class MeetingWindow:
    BG = "#1e1e2e"
    FG = "#cdd6f4"
    MIC = "#89b4fa"       # 🎤 Du       → blau
    SPK = "#f9e2af"       # 🔊 Gegenüber → gelb
    CLAUDE = "#a6e3a1"    # Erläuterung → grün
    SYS = "#6c7086"

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("📋  Meeting — Transkript + Live-Erläuterung")
        root.geometry("880x640")
        root.configure(bg=self.BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._closing = False

        mono = tkfont.nametofont("TkFixedFont").copy()
        mono.configure(size=11)
        fam = mono.actual("family")

        self.text = scrolledtext.ScrolledText(
            root, wrap="word", bg=self.BG, fg=self.FG,
            insertbackground=self.FG, font=mono, relief="flat",
            padx=14, pady=12, state="disabled",
        )
        self.text.pack(fill="both", expand=True)
        self.text.tag_config("mic", foreground=self.MIC, font=(fam, 11, "bold"))
        self.text.tag_config("spk", foreground=self.SPK, font=(fam, 11, "bold"))
        self.text.tag_config("claude", foreground=self.CLAUDE)
        self.text.tag_config("sys", foreground=self.SYS, font=(fam, 10, "italic"))

        bottom = tk.Frame(root, bg="#181825")
        bottom.pack(fill="x", side="bottom")
        self.stop_btn = tk.Button(
            bottom, text="⏹  Meeting beenden + Protokoll", command=self.on_close,
            bg="#f38ba8", fg="#11111b", activebackground="#eba0ac",
            relief="flat", padx=12, pady=4, font=(fam, 10, "bold"),
        )
        self.stop_btn.pack(side="right", padx=10, pady=6)
        self.status = tk.Label(
            bottom, text="⏳ Starte…", bg="#181825", fg=self.SYS,
            anchor="w", padx=12, pady=6, font=(fam, 10),
        )
        self.status.pack(fill="x", side="left", expand=True)

        self._append(
            f"Meeting gestartet — Transkript: {TRANSCRIPT_PATH}\n"
            "🎤 Du (Mikrofon) und 🔊 Gegenüber (Lautsprecher) werden mitgehört. "
            "Nach jeder Sprechpause erläutert Claude den Inhalt kurz als "
            "Stichpunkte. Beenden erzeugt das Protokoll.\n\n", "sys",
        )
        self.root.after(80, self._poll)

    def _append(self, s: str, tag: str):
        self.text.configure(state="normal")
        self.text.insert("end", s, tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, payload = gui_queue.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                elif kind == "turn":
                    ts, label, txt = payload
                    tag = "mic" if "Du" in label else "spk"
                    self._append(f"[{ts}] {label}:  ", tag)
                    self._append(txt + "\n", tag)
                elif kind == "claude":
                    self._append(payload.rstrip() + "\n\n", "claude")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        _stop.set()
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="📝 Erzeuge Protokoll…")
        self._append("\n📝 Meeting beendet — Protokoll wird erstellt…\n", "sys")
        threading.Thread(target=self._finish, daemon=True).start()

    def _finish(self):
        result = generate_protocol()
        if os.path.isabs(result) and os.path.exists(result):
            msg = f"✅ Protokoll gespeichert: {result}\n"
            try:
                subprocess.Popen(["xdg-open", result],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            msg = f"⚠️  {result}\n   Transkript liegt unter: {TRANSCRIPT_PATH}\n"
        self.root.after(0, lambda: self._append(msg, "sys"))
        self.root.after(0, lambda: self.status.configure(text="Fertig — Fenster schließt in 8 s"))
        self.root.after(8000, lambda: (self.root.destroy(), os._exit(0)))


# ── Start ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    from shutil import which

    parser = argparse.ArgumentParser(
        description="Meeting-Modus: Transkript + Live-Stichpunkte + Protokoll",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--no-mic", action="store_true", help="Mikrofon nicht mithören")
    parser.add_argument("--no-speaker", action="store_true", help="Lautsprecher nicht mithören")
    args = parser.parse_args()

    if args.no_mic and args.no_speaker:
        print("✗ Beide Quellen deaktiviert — nichts zu tun.")
        sys.exit(1)
    if not which("claude"):
        print("✗ `claude` (Claude Code CLI) nicht im PATH gefunden.")
        sys.exit(1)
    if not which("parec"):
        print("✗ `parec` (pulseaudio-utils) nicht im PATH gefunden.")
        sys.exit(1)

    _lock = _acquire_lock()
    if _lock is None:
        print("⚠️  Es läuft bereits ein Meeting.")
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda *_: (_stop.set(), os._exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (_stop.set(), os._exit(0)))

    print("📥 Lade Whisper-Modell…")
    base.get_whisper_model()

    _init_transcript()
    print(f"📄 Transkript: {TRANSCRIPT_PATH}")

    sources = []
    if not args.no_mic:
        mic = default_mic_source()
        print(f"🎤 Mikrofon-Quelle:  {mic}")
        sources.append(VADSource("🎤 Du", mic))
    if not args.no_speaker:
        spk = default_speaker_source()
        print(f"🔊 Speaker-Monitor:  {spk}")
        sources.append(VADSource("🔊 Gegenüber", spk))

    threading.Thread(target=turn_worker, daemon=True).start()
    for s in sources:
        s.start()

    root = tk.Tk()
    MeetingWindow(root)
    gui_queue.put(("status", "🎧 Meeting läuft — höre zu…"))
    root.mainloop()


# ── Single-Instance (eigene Lock-Datei) ──────────────────────────────────────
_lock_fd = None


def _acquire_lock():
    import fcntl
    global _lock_fd
    path = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
        f"desktop_transcription_meeting.{os.getuid()}.lock",
    )
    _lock_fd = open(path, "a+")
    try:
        fcntl.flock(_lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    _lock_fd.seek(0)
    _lock_fd.truncate()
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
    return _lock_fd


if __name__ == "__main__":
    main()
