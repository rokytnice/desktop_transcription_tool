"""
transcription_duplex_claude.py — Kontinuierliches Mithören von Mikrofon UND
Lautsprecher, chunkweise an Claude, Antwort im Hauptfenster.

WAS ES MACHT
    Zwei Audioquellen werden GLEICHZEITIG und DAUERHAFT mitgeschnitten:
      🎤 Mikrofon      — die Default-Aufnahmequelle (@DEFAULT_SOURCE@)
      🔊 Speaker       — der Monitor des Default-Ausgabegeräts (…​.monitor),
                         also alles, was aus den Lautsprechern kommt
                         (Videocall-Gegenüber, Video, Musik mit Sprache …).

    Jede Quelle läuft durch eine ZWEISTUFIGE VAD-Segmentierung, damit der Text
    als STREAM erscheint:
      • Mikro-Pause (>= DUPLEX_MICRO_SILENCE) → schneidet einen Chunk, der sofort
        transkribiert und live ins Fenster gestreamt wird.
      • längere Pause (>= DUPLEX_TURN_SILENCE) → der gesammelte Turn (alle Chunks)
        geht als EIN Prompt an Claude.
    Alle Turns laufen serialisiert durch EINE Claude-Session
    (`claude -p --session-id` / `--resume`) → Gesprächskontext bleibt erhalten.
    Claudes Antwort wird live ins Hauptfenster gestreamt.

    Kein Alt+Alt, kein Tippen am Cursor: das Tool läuft von allein und gibt
    ausschließlich im eigenen Fenster aus.

VERWENDUNG
    ./run_duplex_claude.sh              # Mikro + Speaker
    ./run_duplex_claude.sh --no-speaker # nur Mikro
    ./run_duplex_claude.sh --no-mic     # nur Speaker

UMGEBUNGSVARIABLEN
    WHISPER_MODEL         tiny|base|small|medium|large      (Standard: small)
    STREAM_SILENCE_RMS    Schwelle Stille-Erkennung          (Standard: 0.010)
    DUPLEX_MICRO_SILENCE  kurze Pause → Live-Chunk in s       (Standard: 0.35)
    DUPLEX_TURN_SILENCE   längere Pause → Turn an Claude in s  (Standard: 1.1)
    DUPLEX_MIN_CHUNK      Mindestlänge Live-Chunk in s        (Standard: 0.25)
    DUPLEX_MAX_TURN       Turn-Notbremse (Monolog) in s       (Standard: 30.0)
    CLAUDE_CWD            Arbeitsverzeichnis für `claude`      (Standard: ~)
    CLAUDE_MODEL         optionales Modell für `claude -p`
    CLAUDE_PERMISSION_MODE  optional (z.B. plan, acceptEdits)
    MIC_SOURCE           parec-Quelle Mikro (Standard: @DEFAULT_SOURCE@)
    SPEAKER_SOURCE       parec-Quelle Monitor (Standard: <default-sink>.monitor)

HINWEIS (Echo)
    Das Mikrofon nimmt bei offenen Lautsprechern auch den Speaker-Ton auf →
    Phrasen können doppelt ankommen (Mikro + Monitor). Für saubere Trennung
    Kopfhörer nutzen oder mit --no-mic / --no-speaker eine Quelle abschalten.
"""

import os
import sys
import queue
import signal
import threading
import subprocess
import uuid

import numpy as np

# Whisper-Modell, VAD-Konstanten und transcribe_chunk aus dem vad-Modul teilen.
import transcription_streaming as base

import tkinter as tk
from tkinter import scrolledtext
import tkinter.font as tkfont


# ── Claude-Konfiguration (identisch zum claude-Modus) ────────────────────────
CLAUDE_CWD = os.environ.get("CLAUDE_CWD", os.path.expanduser("~"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
CLAUDE_PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "").strip()
SESSION_ID = str(uuid.uuid4())   # eine Session pro Lauf → Gesprächskontext
_first_turn = True               # 1. Turn legt Session an, danach --resume
_claude_lock = threading.Lock()  # nie zwei `claude`-Aufrufe gleichzeitig

# Thread-sichere Brücke Worker → GUI.
gui_queue: "queue.Queue[tuple]" = queue.Queue()
# Serialisiert alle erkannten Phrasen (label, text) zu genau EINEM Claude-Turn.
phrase_queue: "queue.Queue[tuple]" = queue.Queue()

_stop = threading.Event()


# ── Stream-Chunking (Mikro-Pausen) ───────────────────────────────────────────
# Zweistufige Segmentierung, damit die Transkription als STREAM erscheint:
#   • MICRO_SILENCE  — schon eine *kurze* Pause schneidet einen Chunk, der sofort
#                      transkribiert und live ins Fenster gestreamt wird.
#   • TURN_SILENCE   — erst eine *längere* Pause beendet den Turn; dann geht der
#                      gesammelte Text als EIN Prompt an Claude (statt jeden
#                      Mini-Chunk einzeln → sonst antwortet Claude auf Fragmente).
# Wer wirklich pro Mikro-Chunk an Claude will: DUPLEX_TURN_SILENCE == MICRO setzen.
def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


MICRO_SILENCE = _envf("DUPLEX_MICRO_SILENCE", 0.35)   # s – kurze Pause → Live-Chunk
TURN_SILENCE = max(_envf("DUPLEX_TURN_SILENCE", 1.1), MICRO_SILENCE)  # s – Turn-Ende → Claude
MIN_CHUNK = _envf("DUPLEX_MIN_CHUNK", 0.25)           # s – Mindestlänge Live-Chunk
MAX_TURN = _envf("DUPLEX_MAX_TURN", 30.0)             # s – Turn-Notbremse (Monolog)


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
    """Liest eine PulseAudio/PipeWire-Quelle über `parec` als 16 kHz float32-Mono,
    segmentiert an Sprechpausen (identische Logik wie StreamingTranscriber._worker)
    und legt jede fertige Phrase als (label, audio) in die phrase-Pipeline."""

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
            "--client-name=duplex-claude",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _emit_micro(self, seg, seg_samples):
        """Transkribiert einen Mikro-Chunk und streamt ihn live ins Fenster.
        Gibt den erkannten Text zurück (oder None), damit der Turn ihn sammelt."""
        if seg_samples < MIN_CHUNK * base.samplerate:
            return None
        audio = np.concatenate(seg).astype(np.float32)
        text = base.transcribe_chunk(audio)
        if text and text.strip():
            t = text.strip()
            gui_queue.put(("live", (self.label, t)))   # Stream: sofort anzeigen
            return t
        return None

    def _flush_turn(self, texts):
        """Übergibt den gesammelten Turn (alle Mikro-Chunks) als EINEN Prompt an Claude."""
        joined = " ".join(t for t in texts if t).strip()
        if joined:
            phrase_queue.put((self.label, joined))

    def run(self):
        while not _stop.is_set():
            try:
                proc = self._spawn()
            except FileNotFoundError:
                gui_queue.put(("status", "✗ `parec` (pulseaudio-utils) nicht gefunden"))
                return
            # Zweistufige Segmentierung: micro_seg = aktueller Live-Chunk,
            # utter_texts = alle Chunks des laufenden Turns (→ Claude bei Turn-Ende).
            micro_seg, micro_samples = [], 0
            utter_texts = []
            silence_run, turn_samples = 0.0, 0
            in_turn, micro_emitted = False, False
            try:
                while not _stop.is_set():
                    data = proc.stdout.read(self.block_bytes)
                    if len(data) < self.block_bytes:
                        break  # Quelle verloren/EOF → neu verbinden
                    block = np.frombuffer(data, dtype=np.float32)
                    rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0

                    if rms >= base.SILENCE_RMS:
                        in_turn = True
                        micro_emitted = False
                        micro_seg.append(block)
                        micro_samples += len(block)
                        turn_samples += len(block)
                        silence_run = 0.0
                    elif in_turn:
                        micro_seg.append(block)
                        micro_samples += len(block)
                        turn_samples += len(block)
                        silence_run += self.block_dur
                        # Mikro-Pause → einen Live-Chunk schneiden (einmal pro Pause).
                        if not micro_emitted and silence_run >= MICRO_SILENCE:
                            t = self._emit_micro(micro_seg, micro_samples)
                            if t:
                                utter_texts.append(t)
                            micro_seg, micro_samples = [], 0
                            micro_emitted = True
                        # Längere Pause → Turn abschließen, an Claude geben.
                        if silence_run >= TURN_SILENCE:
                            self._flush_turn(utter_texts)
                            micro_seg, micro_samples, utter_texts = [], 0, []
                            silence_run, turn_samples = 0.0, 0
                            in_turn, micro_emitted = False, False
                    # Mikro-Chunk-Notbremse: Dauerredner ohne jede Pause.
                    if micro_samples >= base.MAX_PHRASE * base.samplerate:
                        t = self._emit_micro(micro_seg, micro_samples)
                        if t:
                            utter_texts.append(t)
                        micro_seg, micro_samples, micro_emitted = [], 0, True
                    # Turn-Notbremse: langer Monolog → trotzdem an Claude geben.
                    if turn_samples >= MAX_TURN * base.samplerate:
                        self._flush_turn(utter_texts)
                        micro_seg, micro_samples, utter_texts = [], 0, []
                        silence_run, turn_samples = 0.0, 0
                        in_turn, micro_emitted = False, False
            finally:
                try:
                    proc.kill()
                except Exception:
                    pass
            if not _stop.is_set():
                base.logger.warning(f"[{self.label}] parec-Quelle beendet — neu verbinden…")
                _stop.wait(1.0)


# ── Claude aufrufen (streamt Antwort ins Fenster) ────────────────────────────
def ask_claude(prompt: str):
    """Übergibt den Prompt an `claude -p` und streamt die Antwort in die GUI."""
    global _first_turn
    with _claude_lock:
        if _first_turn:
            cmd = ["claude", "-p", "--session-id", SESSION_ID]
            _first_turn = False
        else:
            cmd = ["claude", "-p", "--resume", SESSION_ID]
        if CLAUDE_MODEL:
            cmd += ["--model", CLAUDE_MODEL]
        if CLAUDE_PERMISSION_MODE:
            cmd += ["--permission-mode", CLAUDE_PERMISSION_MODE]
        cmd += [prompt]

        base.logger.info(f"claude cmd: {' '.join(cmd[:-1])} <prompt {len(prompt)} chars>")
        gui_queue.put(("claude_start", None))
        try:
            proc = subprocess.Popen(
                cmd, cwd=CLAUDE_CWD, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1,
            )
        except FileNotFoundError:
            gui_queue.put(("claude_chunk", "[Fehler: `claude` nicht im PATH]"))
            gui_queue.put(("claude_end", None))
            return

        got_output = False
        for chunk in iter(lambda: proc.stdout.read(64), ""):
            if chunk:
                got_output = True
                gui_queue.put(("claude_chunk", chunk))
        proc.wait()
        if not got_output:
            err = (proc.stderr.read() or "").strip()
            gui_queue.put(("claude_chunk", f"[keine Antwort] {err}" if err else "[keine Antwort]"))
        gui_queue.put(("claude_end", None))


def claude_worker():
    """Nimmt Phrasen aus der Pipeline und übergibt sie EINE nach der anderen an
    Claude — so bleibt der Session-Kontext konsistent und Aufrufe kollidieren nicht."""
    while not _stop.is_set():
        try:
            label, text = phrase_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        # Der Turn-Text wurde bereits live gestreamt (siehe "live"-Events) —
        # hier nicht erneut anzeigen, nur an Claude geben.
        gui_queue.put(("status", "🤔 Claude denkt…"))
        # Quelle im Prompt kennzeichnen, damit Claude den Kontext einordnen kann.
        ask_claude(f"[{label}] {text}")
        gui_queue.put(("status", "🎧 Höre zu (Mikro + Speaker)…"))


# ── GUI (Hauptfenster) ────────────────────────────────────────────────────────
class DuplexWindow:
    BG = "#1e1e2e"
    FG = "#cdd6f4"
    MIC = "#89b4fa"       # Mikrofon → blau
    SPK = "#f9e2af"       # Speaker  → gelb
    CLAUDE = "#a6e3a1"    # Claude   → grün
    SYS = "#6c7086"

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("🎧  Duplex → Claude Code")
        root.geometry("820x600")
        root.configure(bg=self.BG)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        mono = tkfont.nametofont("TkFixedFont").copy()
        mono.configure(size=11)

        self.text = scrolledtext.ScrolledText(
            root, wrap="word", bg=self.BG, fg=self.FG,
            insertbackground=self.FG, font=mono, relief="flat",
            padx=14, pady=12, state="disabled",
        )
        self.text.pack(fill="both", expand=True)
        fam = mono.actual("family")
        self.text.tag_config("mic", foreground=self.MIC, font=(fam, 11, "bold"))
        self.text.tag_config("spk", foreground=self.SPK, font=(fam, 11, "bold"))
        self.text.tag_config("claude", foreground=self.CLAUDE)
        self.text.tag_config("sys", foreground=self.SYS, font=(fam, 10, "italic"))

        self.status = tk.Label(
            root, text="⏳ Starte…", bg="#181825", fg=self.SYS,
            anchor="w", padx=12, pady=6, font=(fam, 10),
        )
        self.status.pack(fill="x", side="bottom")

        self._live_label = None  # aktuell live streamende Quelle (für Zeilenumbrüche)

        self._append(
            "Duplex-Modus: Mikrofon 🎤 und Lautsprecher 🔊 werden dauerhaft "
            "mitgehört. Der Text erscheint als Stream (Chunks an Mikro-Pausen); "
            "nach einer längeren Pause geht der Turn an Claude, die Antwort "
            "erscheint hier. Fenster schließen zum Beenden.\n\n", "sys",
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
                elif kind == "live":
                    # Stream: Mikro-Chunk sofort anzeigen, Label nur bei
                    # Quellenwechsel/Zeilenanfang, sonst Text fortlaufend anhängen.
                    label, txt = payload
                    tag = "mic" if "Mikro" in label else "spk"
                    if label != self._live_label:
                        if self._live_label is not None:
                            self._append("\n", tag)
                        self._append(f"{label} ", tag)
                        self._live_label = label
                    self._append(txt + " ", tag)
                elif kind == "user":  # Fallback (aktuell ungenutzt)
                    label, txt = payload
                    tag = "mic" if "Mikro" in label else "spk"
                    self._append(f"{label}  {txt}\n", tag)
                    self._live_label = None
                elif kind == "claude_start":
                    if self._live_label is not None:
                        self._append("\n", "sys")
                        self._live_label = None
                    self._append("🤖 Claude:\n", "sys")
                elif kind == "claude_chunk":
                    self._append(payload, "claude")
                elif kind == "claude_end":
                    self._append("\n\n", "claude")
                    self._live_label = None
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def on_close(self):
        _stop.set()
        self.root.destroy()
        os._exit(0)


# ── Start ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    from shutil import which

    parser = argparse.ArgumentParser(
        description="Duplex-Transkription (Mikro + Speaker) → claude -p → Fenster",
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

    # Eigener Single-Instance-Lock (unabhängig vom Cursor-Tipp-Lock der anderen
    # Modi): zwei Duplex-Instanzen würden Claude-Turns verdoppeln.
    _lock = _acquire_lock()
    if _lock is None:
        print("⚠️  Es läuft bereits eine Duplex-Instanz.")
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda *_: (_stop.set(), os._exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (_stop.set(), os._exit(0)))

    print("📥 Lade Whisper-Modell…")
    base.get_whisper_model()

    sources = []
    if not args.no_mic:
        mic = default_mic_source()
        print(f"🎤 Mikrofon-Quelle:  {mic}")
        sources.append(VADSource("🎤 Mikro:", mic))
    if not args.no_speaker:
        spk = default_speaker_source()
        print(f"🔊 Speaker-Monitor:  {spk}")
        sources.append(VADSource("🔊 Speaker:", spk))

    print(f"🧠 Claude-Session:   {SESSION_ID}  (cwd: {CLAUDE_CWD})")

    threading.Thread(target=claude_worker, daemon=True).start()
    for s in sources:
        s.start()

    root = tk.Tk()
    DuplexWindow(root)
    gui_queue.put(("status", "🎧 Höre zu (Mikro + Speaker)…"))
    root.mainloop()


# ── Single-Instance (eigene Lock-Datei) ──────────────────────────────────────
_lock_fd = None


def _acquire_lock():
    import fcntl
    global _lock_fd
    path = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
        f"desktop_transcription_duplex.{os.getuid()}.lock",
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
