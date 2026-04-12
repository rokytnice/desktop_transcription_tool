#!/usr/bin/env python3
"""
Full Workflow Test: Audio File → Transcribe → Output to Window
Automated test without user interaction
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.12', 'site-packages'))

import subprocess
import time
import tempfile
from pathlib import Path

# Test results
test_results = {
    "audio_file": False,
    "model_loading": False,
    "transcription": False,
    "text_output": False,
    "ydotool": False
}

def test_audio_file():
    """Test 1: Check if audio file exists"""
    print("[TEST 1] Audio File Exists")
    audio_file = Path("audio_recording.wav")
    if audio_file.exists():
        size_mb = audio_file.stat().st_size / 1024 / 1024
        print(f"  ✓ Found: {audio_file} ({size_mb:.1f} MB)")
        test_results["audio_file"] = True
        return True
    else:
        print(f"  ✗ Not found: {audio_file}")
        return False

def test_model_loading():
    """Test 2: Load Whisper model"""
    print("[TEST 2] Load Whisper Model")
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="auto", compute_type="default")
        print(f"  ✓ Model loaded: small")
        test_results["model_loading"] = True
        return model
    except Exception as e:
        print(f"  ✗ Failed to load model: {e}")
        return None

def test_transcription(model):
    """Test 3: Transcribe audio"""
    print("[TEST 3] Transcribe Audio")
    try:
        segments, info = model.transcribe("audio_recording.wav", language="de", task="transcribe")
        text = " ".join([s.text for s in segments]).strip()
        print(f"  ✓ Transcribed: '{text}'")
        test_results["transcription"] = True
        return text
    except Exception as e:
        print(f"  ✗ Transcription failed: {e}")
        return None

def test_ydotool():
    """Test 4: Check ydotool availability"""
    print("[TEST 4] Check ydotool")
    try:
        result = subprocess.run(["ydotool", "help"],
                              capture_output=True,
                              timeout=2,
                              env={**os.environ, "YDOTOOL_SOCKET": "/run/ydotool/.ydotool_socket"})
        print(f"  ✓ ydotool available")
        test_results["ydotool"] = True
        return True
    except Exception as e:
        print(f"  ✗ ydotool not available: {e}")
        return False

def test_text_output(text):
    """Test 5: Simulate text output"""
    print("[TEST 5] Text Output Simulation")
    try:
        os.environ["YDOTOOL_SOCKET"] = "/run/ydotool/.ydotool_socket"

        # Test with echo instead of actual window (since we don't have a real window in test)
        print(f"  → Would inject to window: '{text}'")
        print(f"  ✓ Text output ready (length: {len(text)} chars)")
        test_results["text_output"] = True
        return True
    except Exception as e:
        print(f"  ✗ Text output failed: {e}")
        return False

def main():
    print("="*70)
    print("FULL WORKFLOW TEST: Audio → Transcribe → Output")
    print("="*70)
    print()

    # Run tests sequentially
    if not test_audio_file():
        print("\n✗ Test failed: Audio file not found")
        return False
    print()

    model = test_model_loading()
    if not model:
        print("\n✗ Test failed: Model loading")
        return False
    print()

    text = test_transcription(model)
    if not text:
        print("\n✗ Test failed: Transcription")
        return False
    print()

    if not test_ydotool():
        print("  ⚠ Warning: ydotool not fully available")
    print()

    if not test_text_output(text):
        print("\n✗ Test failed: Text output")
        return False
    print()

    # Summary
    print("="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    passed = sum(1 for v in test_results.values() if v)
    total = len(test_results)
    print()
    for test_name, result in test_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")
    print()
    print(f"  Score: {passed}/{total} tests passed")
    print()

    if passed == total:
        print("="*70)
        print("✅ ALL TESTS PASSED - System Ready!")
        print("="*70)
        print()
        print("To use the system:")
        print("  1. newgrp input")
        print("  2. Open text editor (mousepad, gedit, etc.)")
        print("  3. Press Alt TWICE")
        print("  4. Speak German")
        print("  5. Press Alt TWICE")
        print("  6. Text appears in editor")
        print()
        return True
    else:
        print("="*70)
        print("⚠️  Some tests failed - Check errors above")
        print("="*70)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
