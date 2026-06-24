#!/usr/bin/env python3
"""
Sprich-mit-Claude-Code — Sprache → Claude Code → Fenster.

Statt den transkribierten Text an der Cursor-Position zu tippen, wird er als
Prompt an die Claude-Code-CLI (`claude -p`) übergeben; Claudes Antwort erscheint
live in einem eigenen Fenster (Tkinter). Über `--session-id` bleibt der Kontext
über mehrere Sprach-Eingaben hinweg erhalten — es entsteht ein echtes Gespräch.

Bedienung (wie bei den anderen Modi):
  Alt+Alt   Aufnahme starten
  Alt+Alt   Aufnahme stoppen → transkribieren → an Claude übergeben
  Ctrl+C / Fenster schließen   Beenden

Aufnahme, Whisper-Transkription, Geräteauswahl und die Alt+Alt-Erkennung werden
aus transcription_offline.py wiederverwendet; hier wird nur die Ausgabe ersetzt.

Umgebungsvariablen:
  WHISPER_MODEL          Whisper-Modell (Standard: small)
  AUDIO_DEVICE           Input-Device Index
  AUDIO_OUTPUT_DEVICE    Output-Device Index (Beeps)
  CLAUDE_CWD             Arbeitsverzeichnis für Claude  (Standard: $HOME)
  CLAUDE_MODEL           Modell für Claude (z. B. sonnet, opus)  (optional)
  CLAUDE_PERMISSION_MODE Permission-Mode (z. B. plan, acceptEdits)  (optional)
"""

import os
import sys
import uuid
import queue
import signal
import threading
import subprocess

import tkinter as tk
from tkinter import scrolledtext, font as tkfont

# Aufnahme/Transkription/Tastatur aus dem Offline-Modus wiederverwenden.
import transcription_offline as base

# ── Claude-Konfiguration ─────────────────────────────────────────────────────
CLAUDE_CWD = os.environ.get("CLAUDE_CWD", os.path.expanduser("~"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
CLAUDE_PERMISSION_MODE = os.environ.get("CLAUDE_PERMISSION_MODE", "").strip()
SESSION_ID = str(uuid.uuid4())  # eine Session pro Lauf → Gesprächskontext
_first_turn = True              # 1. Turn legt Session an, danach --resume

# Thread-sichere Brücke Worker → GUI.
gui_queue: "queue.Queue[tuple]" = queue.Queue()


# ── Claude aufrufen (streamt Antwort ins Fenster) ────────────────────────────
def ask_claude(prompt: str):
    """Übergibt den Prompt an `claude -p` und schiebt die Antwort live in die GUI."""
    global _first_turn
    # --session-id legt die Session an; Folge-Turns setzen sie mit --resume fort
    # (gleiche ID erneut mit --session-id → "already in use"). So bleibt der
    # Gesprächskontext über mehrere Sprach-Eingaben erhalten.
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
            cmd,
            cwd=CLAUDE_CWD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        gui_queue.put(("claude_chunk", "[Fehler: `claude` nicht im PATH gefunden]"))
        gui_queue.put(("claude_end", None))
        return

    got_output = False
    # stdout zeichenweise lesen → Antwort erscheint, während sie entsteht.
    for chunk in iter(lambda: proc.stdout.read(64), ""):
        if chunk:
            got_output = True
            gui_queue.put(("claude_chunk", chunk))
    proc.wait()

    if not got_output:
        err = (proc.stderr.read() or "").strip()
        gui_queue.put(("claude_chunk", f"[keine Antwort] {err}" if err else "[keine Antwort]"))
    gui_queue.put(("claude_end", None))


# ── Ausgabe-Hooks: Offline-Verhalten ersetzen ───────────────────────────────
def transcribe_and_output():
    """Ersetzt base.transcribe_and_output: statt Clipboard → Claude → Fenster."""
    try:
        gui_queue.put(("status", "🧠 Transkribiere…"))
        text = base.transcribe_with_whisper(base.file_path)
        if not text or not text.strip():
            gui_queue.put(("status", "⚠️  Nichts erkannt — Alt+Alt zum erneut Sprechen."))
            return
        text = text.strip()
        gui_queue.put(("user", text))
        gui_queue.put(("status", "🤔 Claude denkt…"))
        base.play_stop_recording_sound()
        ask_claude(text)
        gui_queue.put(("status", "✅ Bereit — Alt+Alt zum Sprechen."))
    except Exception as e:
        base.logger.error(f"transcribe_and_output (claude) failed: {e}")
        gui_queue.put(("status", f"✗ Fehler: {e}"))


def _start_recording_hook():
    gui_queue.put(("status", "🔴 Aufnahme läuft — Alt+Alt zum Stoppen."))
    _orig_start_recording()


# Monkeypatch: die Alt+Alt-Logik in base ruft diese Namen als Modul-Globals auf.
_orig_start_recording = base.start_recording
base.start_recording = _start_recording_hook
base.transcribe_and_output = transcribe_and_output


# ── GUI ──────────────────────────────────────────────────────────────────────
class ChatWindow:
    BG = "#1e1e2e"
    FG = "#cdd6f4"
    USER = "#89b4fa"
    CLAUDE = "#a6e3a1"
    SYS = "#6c7086"

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("🎙️  Sprich mit Claude Code")
        root.geometry("760x560")
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
        self.text.tag_config("user", foreground=self.USER, font=(mono.actual("family"), 11, "bold"))
        self.text.tag_config("claude", foreground=self.CLAUDE)
        self.text.tag_config("sys", foreground=self.SYS, font=(mono.actual("family"), 10, "italic"))

        self.status = tk.Label(
            root, text="⏳ Starte…", bg="#181825", fg=self.SYS,
            anchor="w", padx=12, pady=6, font=(mono.actual("family"), 10),
        )
        self.status.pack(fill="x", side="bottom")

        self._append(
            "Sprich mit Claude Code — Alt+Alt startet die Aufnahme, Alt+Alt "
            "stoppt sie. Dein gesprochener Text geht an Claude, die Antwort "
            "erscheint hier.\n\n", "sys",
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
                elif kind == "user":
                    self._append(f"🗣  Du:  {payload}\n", "user")
                elif kind == "claude_start":
                    self._append("🤖 Claude:\n", "sys")
                elif kind == "claude_chunk":
                    self._append(payload, "claude")
                elif kind == "claude_end":
                    self._append("\n\n", "claude")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def on_close(self):
        base._shutdown_requested = True
        self.root.destroy()
        os._exit(0)


# ── Start ────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Sprich-mit-Claude-Code — Sprache → claude -p → Fenster",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-d", "--default", action="store_true",
                        help="Schnellstart: Default-Geräte ohne Auswahl-Menü")
    parser.add_argument("-a", "--auto", action="store_true",
                        help="Ein Gerät für Input UND Output auswählen")
    args = parser.parse_args()

    # Nur EINE Transcription-Instanz darf laufen (teilt Tastatur + Mikro).
    import _singleinstance
    _singleinstance.acquire_or_exit()

    if not subprocess_which("claude"):
        print("✗ `claude` (Claude Code CLI) nicht im PATH gefunden.")
        sys.exit(1)

    signal.signal(signal.SIGINT, base._signal_handler)
    signal.signal(signal.SIGTERM, base._signal_handler)

    interactive = not args.default
    try:
        base.get_whisper_model()
    except Exception as e:
        print(f"Error loading Whisper model: {e}")

    try:
        if args.auto:
            base.select_auto_device()
        else:
            base.select_audio_device(interactive=interactive)
            try:
                base.select_output_device(interactive=interactive)
            except Exception as e:
                print(f"Error selecting output device: {e}")
    except Exception as e:
        print(f"Error selecting audio device: {e}")
        sys.exit(1)

    import sounddevice as sd
    if base.device_index is not None and base.output_device_index is not None:
        sd.default.device = [base.device_index, base.output_device_index]

    print("\nDetecting keyboard devices...")
    keyboard_devices = base.find_keyboard_devices()
    print(f"Found {len(keyboard_devices)} keyboard device(s).")
    print(f"Claude-Session: {SESSION_ID}  (cwd: {CLAUDE_CWD})")

    # Tastatur-Überwachung im Hintergrund; Tk-Mainloop auf dem Hauptthread.
    threading.Thread(
        target=base.process_keyboard_events,
        args=(keyboard_devices,),
        daemon=True,
    ).start()

    root = tk.Tk()
    win = ChatWindow(root)
    gui_queue.put(("status", "✅ Bereit — Alt+Alt zum Sprechen."))
    root.mainloop()


def subprocess_which(name: str) -> bool:
    from shutil import which
    return which(name) is not None


if __name__ == "__main__":
    main()
