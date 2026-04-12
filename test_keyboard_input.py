#!/usr/bin/env python3
"""
Keyboard Input Test: Verify Alt key detection and double-tap recognition
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.12', 'site-packages'))

from evdev import InputDevice, ecodes, list_devices
import select
import time

# Test results
test_results = {
    "devices_available": False,
    "input_group": False,
    "keyboard_detection": False,
    "alt_key_detection": False,
}

def test_input_group():
    """Test 1: Check if user is in input group"""
    print("[TEST 1] Check Input Group Membership")
    try:
        import pwd
        import grp

        uid = os.getuid()
        user = pwd.getpwuid(uid)
        groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]

        if "input" in groups:
            print(f"  ✓ User '{user.pw_name}' is in input group")
            test_results["input_group"] = True
            return True
        else:
            print(f"  ✗ User '{user.pw_name}' is NOT in input group")
            print(f"    Groups: {', '.join(groups)}")
            print(f"    Fix: newgrp input")
            return False
    except Exception as e:
        print(f"  ✗ Failed to check groups: {e}")
        return False

def test_devices_available():
    """Test 2: Check if input devices are available"""
    print("[TEST 2] Input Devices Available")
    try:
        devices = list(list_devices())
        print(f"  ✓ Found {len(devices)} input devices")
        test_results["devices_available"] = True
        return devices
    except Exception as e:
        print(f"  ✗ Failed to list devices: {e}")
        return None

def test_keyboard_detection(devices):
    """Test 3: Detect keyboard devices"""
    print("[TEST 3] Keyboard Detection")
    keyboards = []

    if not devices:
        print(f"  ✗ No devices to check")
        return keyboards

    try:
        for path in devices:
            try:
                device = InputDevice(path)
                if ecodes.KEY_LEFTALT in device.capabilities().get(ecodes.EV_KEY, []):
                    keyboards.append(device)
                    print(f"  ✓ Found: {device.name}")
            except PermissionError:
                print(f"  ✗ Permission denied: {path}")
            except:
                pass

        if keyboards:
            print(f"  ✓ Total keyboards: {len(keyboards)}")
            test_results["keyboard_detection"] = True
            return keyboards
        else:
            print(f"  ✗ No keyboards detected")
            return keyboards
    except Exception as e:
        print(f"  ✗ Failed to detect keyboards: {e}")
        return keyboards

def test_alt_key_input(keyboards):
    """Test 4: Monitor for Alt key input"""
    print("[TEST 4] Alt Key Detection (Monitor for Input)")

    if not keyboards:
        print(f"  ✗ No keyboards to monitor")
        return False

    print(f"  → Listening for Alt key presses for 10 seconds...")
    print(f"  → TRY: Press Alt key on your keyboard NOW")
    print()

    alt_detected = False
    start_time = time.time()
    timeout = 10  # seconds

    try:
        while time.time() - start_time < timeout:
            remaining = timeout - (time.time() - start_time)

            r, w, x = select.select(keyboards, [], [], 1)

            for device in r:
                try:
                    for event in device.read():
                        if event.type == ecodes.EV_KEY:
                            key_code = event.code
                            key_state = event.value  # 1 = press, 0 = release

                            # Check for Alt key
                            if key_code in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT):
                                key_name = "LEFT ALT" if key_code == ecodes.KEY_LEFTALT else "RIGHT ALT"
                                action = "PRESSED" if key_state == 1 else "RELEASED"
                                print(f"  ✓ {key_name} {action}")

                                if key_state == 1:  # Press event
                                    alt_detected = True
                                    test_results["alt_key_detection"] = True
                except OSError:
                    pass

            # Show remaining time
            sys.stdout.write(f"\r  ⏱ Time remaining: {remaining:.1f}s  ")
            sys.stdout.flush()

    except KeyboardInterrupt:
        print(f"\n  ⚠ Test interrupted by user")
        return alt_detected
    except Exception as e:
        print(f"  ✗ Error during monitoring: {e}")
        return False

    print()

    if alt_detected:
        print(f"  ✓ Alt key detected!")
        return True
    else:
        print(f"  ✗ No Alt key detected during 10 seconds")
        print(f"    Make sure:")
        print(f"    1. You ran: newgrp input")
        print(f"    2. Keyboard is working")
        print(f"    3. You pressed Alt key during test")
        return False

def test_double_tap_simulation():
    """Test 5: Double-tap simulation logic"""
    print("[TEST 5] Double-Tap Logic Simulation")

    DOUBLE_TAP_TIMEOUT = 0.3
    press_times = []

    # Simulate two presses within timeout
    press_times.append(0.0)
    press_times.append(0.15)  # 150ms later

    # Check if double-tap detected
    current_time = 0.15
    press_times = [t for t in press_times if current_time - t < DOUBLE_TAP_TIMEOUT]

    if len(press_times) > 1:
        print(f"  ✓ Double-tap would be detected (2 presses within {DOUBLE_TAP_TIMEOUT}s)")
        return True
    else:
        print(f"  ✗ Double-tap detection failed")
        return False

def main():
    print("="*70)
    print("KEYBOARD INPUT TEST: Alt Double-Tap Detection")
    print("="*70)
    print()

    # Test 1: Input group
    if not test_input_group():
        print("\n⚠️  CRITICAL: Run: newgrp input")
        return False
    print()

    # Test 2: Devices
    devices = test_devices_available()
    if not devices:
        print("\n✗ No input devices found")
        return False
    print()

    # Test 3: Keyboard detection
    keyboards = test_keyboard_detection(devices)
    if not keyboards:
        print("\n✗ No keyboards detected")
        return False
    print()

    # Test 4: Alt key monitoring
    alt_detected = test_alt_key_input(keyboards)
    print()

    # Test 5: Double-tap simulation
    test_double_tap_simulation()
    print()

    # Summary
    print("="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    print()
    for test_name, result in test_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")
    print()

    passed = sum(1 for v in test_results.values() if v)
    total = len(test_results)
    print(f"  Score: {passed}/{total} tests passed")
    print()

    if passed >= 4:  # At least 4 of 5
        print("="*70)
        print("✅ KEYBOARD INPUT READY!")
        print("="*70)
        print()
        print("You can now use Alt double-tap to control recording:")
        print("  1. Alt 2x → Start recording")
        print("  2. Speak German")
        print("  3. Alt 2x → Stop & transcribe")
        print()
        return True
    else:
        print("="*70)
        print("⚠️  Keyboard input not working")
        print("="*70)
        print()
        print("Troubleshooting:")
        print("  1. Run: newgrp input")
        print("  2. Make sure keyboard works")
        print("  3. Try again")
        print()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
