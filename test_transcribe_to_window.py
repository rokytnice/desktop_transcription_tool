#!/usr/bin/env python3
"""
Quick Test: Transcribe audio_recording.wav → Output to Active Window
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.12', 'site-packages'))

from faster_whisper import WhisperModel
import subprocess
import time

print("="*60)
print("TEST: Transcribe Audio → Output to Window")
print("="*60)
print()

# Step 1: Load Whisper
print("[1/3] Loading Whisper model...")
try:
    model = WhisperModel("small", device="auto", compute_type="default")
    print("✓ Model loaded")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Step 2: Transcribe
print("[2/3] Transcribing audio_recording.wav...")
try:
    segments, info = model.transcribe("audio_recording.wav", language="de", task="transcribe")
    text = " ".join([s.text for s in segments]).strip()
    print(f"✓ Transcribed: {text}")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

print()

# Step 3: Output to window
print("[3/3] Outputting to active window...")
print()
print("INSTRUCTIONS:")
print("  1. Click in a text editor (mousepad, gedit, VS Code, etc.)")
print("  2. Make sure the editor window is ACTIVE (focused)")
print("  3. Press ENTER here to inject the text")
print()

try:
    input("Press ENTER to inject text into active window... ")

    os.environ["YDOTOOL_SOCKET"] = "/run/ydotool/.ydotool_socket"
    subprocess.run(["ydotool", "type", text], check=True, timeout=10)

    print()
    print("✓ Text injected successfully!")
    print(f"✓ Your text: '{text}'")
    print()
    print("="*60)
    print("✓ TEST COMPLETE - Check your editor window!")
    print("="*60)

except KeyboardInterrupt:
    print("\nTest cancelled")
    sys.exit(1)
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)
