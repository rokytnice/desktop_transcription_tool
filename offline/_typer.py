#!/usr/bin/env python3
"""
_typer.py — Text an der aktuellen Cursor-Position tippen (Wayland).

Gemeinsames Tipp-Backend für alle Modi. Tippt den Text direkt dort, wo der
Cursor steht — kein Umweg über die Zwischenablage, kein manuelles Ctrl+V.

Mechanismus je nach Compositor:
  • ydotool  — über /dev/uinput (Kernel-Ebene), funktioniert auf GNOME/KDE
               Wayland. Bevorzugt. Braucht laufenden ydotoold-Daemon (wird bei
               Bedarf selbst gestartet).
  • wtype    — virtual-keyboard-Protokoll, nur wlroots (Sway/Hyprland).
  • wl-copy  — Fallback: nur Zwischenablage, manuelles Ctrl+V nötig.

Verwendung:
    import _typer
    _typer.detect_typer()          # einmal beim Start
    _typer.type_at_cursor("Hallo") # pro Ausgabe
"""

import os
import re
import time
import logging
import subprocess

logger = logging.getLogger(__name__)

YDOTOOL_SOCKET = os.environ.get('YDOTOOL_SOCKET') or f"/run/user/{os.getuid()}/.ydotool_socket"
TYPER = None      # 'ydotool' | 'wtype' | 'clipboard'
KB_LAYOUT = 'us'  # active keyboard layout, set by detect_typer()

# ── ydotool layout fix ──────────────────────────────────────────────────────
# ydotool injects RAW Linux keycodes ("we're using raw keycodes now", its own
# --help) and assumes a US-QWERTY layout. On a German (QWERTZ) compositor that
# swaps Z↔Y and mangles umlauts/punctuation. `ydotool type` has no layout option.
# Fix: when the active layout is German, send the keycodes that produce the
# correct character ON THE GERMAN LAYOUT via `ydotool key` ourselves.
KEY_SHIFT, KEY_ALTGR = 42, 100

# char -> (Linux keycode, modifier or None) for the German T1 (de) layout
_DE_KEYMAP = {
    '1': (2, None),  '!': (2, KEY_SHIFT),
    '2': (3, None),  '"': (3, KEY_SHIFT),
    '3': (4, None),  '§': (4, KEY_SHIFT),
    '4': (5, None),  '$': (5, KEY_SHIFT),
    '5': (6, None),  '%': (6, KEY_SHIFT),
    '6': (7, None),  '&': (7, KEY_SHIFT),
    '7': (8, None),  '/': (8, KEY_SHIFT),
    '8': (9, None),  '(': (9, KEY_SHIFT),
    '9': (10, None), ')': (10, KEY_SHIFT),
    '0': (11, None), '=': (11, KEY_SHIFT),
    'ß': (12, None), '?': (12, KEY_SHIFT),
    'q': (16, None), 'Q': (16, KEY_SHIFT), '@': (16, KEY_ALTGR),
    'w': (17, None), 'W': (17, KEY_SHIFT),
    'e': (18, None), 'E': (18, KEY_SHIFT), '€': (18, KEY_ALTGR),
    'r': (19, None), 'R': (19, KEY_SHIFT),
    't': (20, None), 'T': (20, KEY_SHIFT),
    'z': (21, None), 'Z': (21, KEY_SHIFT),
    'u': (22, None), 'U': (22, KEY_SHIFT),
    'i': (23, None), 'I': (23, KEY_SHIFT),
    'o': (24, None), 'O': (24, KEY_SHIFT),
    'p': (25, None), 'P': (25, KEY_SHIFT),
    'ü': (26, None), 'Ü': (26, KEY_SHIFT),
    '+': (27, None), '*': (27, KEY_SHIFT),
    'a': (30, None), 'A': (30, KEY_SHIFT),
    's': (31, None), 'S': (31, KEY_SHIFT),
    'd': (32, None), 'D': (32, KEY_SHIFT),
    'f': (33, None), 'F': (33, KEY_SHIFT),
    'g': (34, None), 'G': (34, KEY_SHIFT),
    'h': (35, None), 'H': (35, KEY_SHIFT),
    'j': (36, None), 'J': (36, KEY_SHIFT),
    'k': (37, None), 'K': (37, KEY_SHIFT),
    'l': (38, None), 'L': (38, KEY_SHIFT),
    'ö': (39, None), 'Ö': (39, KEY_SHIFT),
    'ä': (40, None), 'Ä': (40, KEY_SHIFT),
    '#': (43, None), "'": (43, KEY_SHIFT),
    '<': (86, None), '>': (86, KEY_SHIFT),
    'y': (44, None), 'Y': (44, KEY_SHIFT),
    'x': (45, None), 'X': (45, KEY_SHIFT),
    'c': (46, None), 'C': (46, KEY_SHIFT),
    'v': (47, None), 'V': (47, KEY_SHIFT),
    'b': (48, None), 'B': (48, KEY_SHIFT),
    'n': (49, None), 'N': (49, KEY_SHIFT),
    'm': (50, None), 'M': (50, KEY_SHIFT),
    ',': (51, None), ';': (51, KEY_SHIFT),
    '.': (52, None), ':': (52, KEY_SHIFT),
    '-': (53, None), '_': (53, KEY_SHIFT),
    ' ': (57, None), '\n': (28, None), '\t': (15, None),
}

# Fold typographic characters Whisper sometimes emits onto keys we can type.
_NORMALIZE = {
    '„': '"', '“': '"', '”': '"', '‚': "'", '‘': "'", '’': "'",
    '–': '-', '—': '-', '…': '...', ' ': ' ',
}


def detect_kb_layout():
    """Best-effort detection of the active keyboard layout (e.g. 'de', 'us')."""
    forced = os.environ.get('STREAM_KBLAYOUT')
    if forced:
        return forced.strip().lower()
    for key in ('mru-sources', 'sources'):
        try:
            r = subprocess.run(
                ['gsettings', 'get', 'org.gnome.desktop.input-sources', key],
                capture_output=True, text=True, timeout=3)
            m = re.search(r"'xkb',\s*'([a-z]{2})", r.stdout)
            if m:
                return m.group(1)
        except Exception:
            pass
    try:
        r = subprocess.run(['localectl', 'status'],
                           capture_output=True, text=True, timeout=3)
        m = re.search(r'X11 Layout:\s*(\w+)', r.stdout)
        if m:
            return m.group(1).split(',')[0].lower()
    except Exception:
        pass
    return 'us'


def _de_key_events(text):
    """Build a ydotool 'key' press/release sequence for `text` on the de layout."""
    text = ''.join(_NORMALIZE.get(c, c) for c in text)
    seq = []
    for ch in text:
        m = _DE_KEYMAP.get(ch)
        if m is None:
            logger.warning(f"de-keymap: no key for {ch!r}, skipped")
            continue
        code, mod = m
        if mod:
            seq.append(f"{mod}:1")
        seq.append(f"{code}:1")
        seq.append(f"{code}:0")
        if mod:
            seq.append(f"{mod}:0")
    return seq


def _ydotool_env():
    env = dict(os.environ)
    env['YDOTOOL_SOCKET'] = YDOTOOL_SOCKET
    return env


def _ydotool_works():
    try:
        r = subprocess.run(['ydotool', 'type', '--file', '-'], input=b'',
                           env=_ydotool_env(), timeout=4, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def ensure_ydotoold():
    """Make sure a usable (user-owned) ydotoold is reachable; start one if not."""
    if _ydotool_works():
        return True
    try:
        subprocess.Popen(
            ['ydotoold', f'--socket-path={YDOTOOL_SOCKET}',
             f'--socket-own={os.getuid()}:{os.getgid()}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(15):
            time.sleep(0.3)
            if _ydotool_works():
                logger.info(f"Started user ydotoold (socket {YDOTOOL_SOCKET})")
                return True
    except FileNotFoundError:
        logger.warning("ydotoold not found")
    return _ydotool_works()


def _wtype_works():
    try:
        r = subprocess.run(['wtype', ''], timeout=4, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def detect_typer():
    """Pick the best available 'type at cursor' backend for this session."""
    global TYPER, KB_LAYOUT
    if ensure_ydotoold():
        TYPER = 'ydotool'
    elif _wtype_works():
        TYPER = 'wtype'
    else:
        TYPER = 'clipboard'
    KB_LAYOUT = detect_kb_layout()
    logger.info(f"Typing backend: {TYPER} (keyboard layout: {KB_LAYOUT})")
    return TYPER


def type_at_cursor(text):
    """Type text at the current cursor position using the detected backend."""
    if not text or not text.strip():
        return
    if TYPER is None:
        # detect_typer() was never called — do it now so a bare call still works.
        detect_typer()
    if TYPER == 'ydotool':
        # German layout: ydotool's raw US keycodes would swap Z/Y and mangle
        # umlauts — emit layout-correct keycodes via `ydotool key` instead.
        if KB_LAYOUT.startswith('de'):
            seq = _de_key_events(text)
            if seq:
                try:
                    subprocess.run(['ydotool', 'key', '-d', '2'] + seq,
                                   env=_ydotool_env(), check=True, timeout=30)
                    return
                except Exception as e:
                    logger.error(f"ydotool key error: {e}")
            else:
                return
        else:
            try:
                # --file - reads from stdin with escaping disabled → literal text,
                # robust for umlauts/special chars and leading '-'.
                subprocess.run(['ydotool', 'type', '-d', '2', '--file', '-'],
                               input=text.encode('utf-8'), env=_ydotool_env(),
                               check=True, timeout=30)
                return
            except Exception as e:
                logger.error(f"ydotool error: {e}")
    elif TYPER == 'wtype':
        try:
            subprocess.run(['wtype', text], check=True, timeout=30)
            return
        except Exception as e:
            logger.error(f"wtype error: {e}")
    # Fallback: clipboard (manual paste)
    try:
        p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
        p.communicate(text.encode('utf-8'))
        print(f"   📋 (kein Direkt-Tippen) in Zwischenablage: {text}")
        print("   🖱️  Mit Ctrl+V einfügen.")
        logger.warning("Used clipboard fallback (Ctrl+V to paste)")
    except Exception as e:
        logger.error(f"Clipboard fallback failed: {e}")
        print(f"   Text: {text}")
