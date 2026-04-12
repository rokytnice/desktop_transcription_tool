#!/usr/bin/env python3

import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import subprocess
import time
import logging
import whisper
import torch
from evdev import InputDevice, ecodes, list_devices
import wave
import select

# Ensure the environment is correctly configured
os.environ["LC_ALL"] = "de_DE.UTF-8"
os.environ["LANG"] = "de_DE.UTF-8"

recording = False
file_path = "audio_recording.wav"
audio_data = []
input_stream = None
recording_start_time = None

samplerate = 48000  # Will be auto-detected in main()
MIN_RECORDING_TIME = 1.5  # Minimum 1.5 seconds of recording

# Logger erstellen
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Ausgabe in eine Datei
file_handler = logging.FileHandler('transcription_listener.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Ausgabe in die Konsole
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

current_keys = set()
ctrl_press_times = []  # Track Ctrl press times for double-tap detection
DOUBLE_TAP_TIMEOUT = 0.3  # Time window for double-tap (in seconds)



def start_recording():
    global recording, audio_data, input_stream, recording_start_time
    if not recording:
        try:
            print("Recording started...")
            recording = True
            recording_start_time = time.time()
            audio_data = []
            input_stream = sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', callback=audio_callback)
            input_stream.start()
            logging.info(f"Recording started with sample rate {samplerate}")
        except Exception as e:
            logging.error(f"Error starting recording: {e}")
            print(f"Error starting recording: {e}")
            recording = False
            input_stream = None

def stop_recording():
    global recording, input_stream, recording_start_time
    if recording:
        try:
            # Check minimum recording time
            elapsed = time.time() - recording_start_time
            if elapsed < MIN_RECORDING_TIME:
                remaining = MIN_RECORDING_TIME - elapsed
                print(f"\nRecording too short ({elapsed:.1f}s). Recording for {remaining:.1f}s more...")
                logging.info(f"Recording too short ({elapsed:.1f}s), waiting for minimum duration")
                time.sleep(remaining)

            print("Recording stopped. Saving file...")
            logging.info("Stop recording called")
            recording = False

            if input_stream is not None:
                try:
                    logging.debug("Stopping input stream...")
                    input_stream.stop()
                    logging.debug("Closing input stream...")
                    input_stream.close()
                    logging.debug("Input stream closed")
                except Exception as e:
                    logging.error(f"Error closing stream: {e}")

            # Wait a bit for final audio data
            time.sleep(0.2)
            save_audio()
            transcribe_and_output()
        except Exception as e:
            logging.error(f"Error in stop_recording: {e}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

def audio_callback(indata, frames, time, status):
    if recording:
        audio_data.append(indata.copy())

def save_audio():
    global audio_data
    try:
        if len(audio_data) == 0:
            print("No audio data to save.")
            return

        audio_array = np.concatenate(audio_data, axis=0)

        # Flatten to 1D if needed
        if audio_array.ndim > 1:
            audio_array = audio_array.flatten()

        # Ensure int16 format
        if audio_array.dtype != np.int16:
            audio_array = audio_array.astype(np.int16)

        # Use wave module to ensure correct int16 writing
        with wave.open(file_path, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 2 bytes for int16
            wav_file.setframerate(samplerate)
            wav_file.writeframes(audio_array.tobytes())

        print(f"Audio saved to {file_path}")
        logging.info(f"Audio saved: {len(audio_array)} samples")
    except Exception as e:
        print(f"Error saving audio: {e}")
        logging.error(f"Error saving audio: {e}")


def transcribe_with_whisper(audio_file_path):
    try:
        model = whisper.load_model("base")
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        result = model.transcribe(audio_file_path,  fp16=True, language="de", task="transcribe")

        transcription = result["text"]
        logging.info(f"Transcription result: {transcription}")

        return transcription

    except Exception as e:
        logging.error(f"Failed to transcribe audio with Whisper: {e}")
        raise

def save_text_to_file(text):
    """Save transcribed text to a file"""
    output_file = os.path.expanduser("~/transcription_output.txt")
    try:
        logging.info(f"Saving text to {output_file}")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        logging.info(f"✓ Text saved successfully to {output_file}")
        return output_file
    except Exception as e:
        logging.error(f"ERROR saving to file: {e}", exc_info=True)
        print(f"❌ Error saving to file: {e}")
        return None

def type_text_in_active_window(text):
    """Copy transcribed text to clipboard for pasting into active window"""
    logging.info(f"Outputting text: {text}")

    print(f"\n" + "="*70)
    print("📄 TRANSCRIPTION OUTPUT")
    print("="*70)
    print(f"\n{text}\n")
    print("="*70)

    # Copy to clipboard using xclip
    try:
        process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))
        logging.info("Text copied to clipboard with xclip")
        print("✓ Text copied to clipboard")
        print("   Paste it with: Ctrl+V")
    except Exception as e:
        logging.error(f"Error copying to clipboard: {e}")
        # Fallback: save to file
        output_file = save_text_to_file(text)
        print(f"Text saved to: {output_file}")
        print(f"Could not use xclip, but text is saved in: gedit {output_file}")


def transcribe_and_output():
    try:
        # Hinweis auf Start der Transkription
        print("\n" + "="*60)
        print("STARTING TRANSCRIPTION...")
        print("="*60)
        logging.info("Starting transcription...")

        transcription = transcribe_with_whisper(file_path)

        if not transcription or transcription.strip() == "":
            print("❌ No valid transcription found.")
            logging.info("No valid transcription generated.")
            return

        # Transkription ausgeben und ins aktive Fenster eingeben
        print(f"\n✓ Transcription result:")
        print(f"   {transcription}")
        logging.info(f"Transcription: {transcription}")

        print(f"\nNow typing into active window...")
        logging.info("Calling type_text_in_active_window()")
        type_text_in_active_window(transcription)
        print("="*60 + "\n")

    except Exception as e:
        logging.error(f"An error occurred during transcription: {e}", exc_info=True)
        print(f"❌ An error occurred during transcription: {e}")


def get_keyboard_devices():
    """Get all keyboard devices"""
    keyboards = []
    for path in list_devices():
        try:
            device = InputDevice(path)
            # Check if device has keyboard keys
            if ecodes.KEY_LEFTCTRL in device.capabilities().get(ecodes.EV_KEY, []):
                keyboards.append(device)
                logging.info(f"Found keyboard: {device.name} ({device.path})")
        except Exception as e:
            logging.debug(f"Skipped device {path}: {e}")
    return keyboards

if __name__ == "__main__":
    logging.info("Script started")

    # Check if xdotool is installed
    try:
        subprocess.run(["xdotool", "--version"], capture_output=True, check=True, timeout=2)
        logging.info(f"✓ xdotool found")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        logging.warning(f"⚠️ xdotool not found")
        print(f"⚠️ WARNING: xdotool not found")
        print(f"   Install with: sudo apt install xdotool")
        print("")

    # Find best sample rate
    try:
        default_device = sd.default.device[0]
        device_info = sd.query_devices(default_device)
        default_rate = int(device_info['default_samplerate'])

        # Try common rates that Whisper likes
        for rate in [16000, 22050, 44100, 48000]:
            try:
                sd.check_input_settings(samplerate=rate, channels=1)
                samplerate = rate
                logging.info(f"Using sample rate: {rate} Hz")
                break
            except:
                continue
        else:
            # Fallback to default
            samplerate = default_rate
            logging.info(f"Using device default sample rate: {samplerate} Hz")
    except Exception as e:
        logging.error(f"Error detecting sample rate: {e}")
        samplerate = 44100  # Final fallback
        logging.info(f"Using fallback sample rate: {samplerate} Hz")

    print("\n" + "="*50)
    print("ALT DOUBLE-TAP MODE")
    print("="*50)
    print("\n  1. Press Alt TWICE quickly to START")
    print("  2. Speak (for as long as you want)")
    print("  3. Press Alt TWICE quickly to STOP & transcribe")
    print("\n" + "="*50 + "\n")
    logging.info("Keyboard listener starting...")

    while True:
        try:
            # Get all keyboard devices
            keyboards = get_keyboard_devices()
            if not keyboards:
                logging.error("No keyboard devices found!")
                print("Error: No keyboard devices found!")
                time.sleep(2)
                continue

            logging.info(f"Keyboard listener active ({len(keyboards)} device(s))")

            # Use select to monitor all devices
            inner_loop_active = True
            while inner_loop_active:
                try:
                    r, w, x = select.select(keyboards, [], [])

                    for device in r:
                        try:
                            for event in device.read():
                                if event.type == ecodes.EV_KEY:
                                    key_code = event.code
                                    key_state = event.value  # 1 = press, 0 = release

                                    # Detect Alt key PRESS (double-tap detection)
                                    if (key_code == ecodes.KEY_LEFTALT or key_code == ecodes.KEY_RIGHTALT) and key_state == 1:
                                        current_time = time.time()

                                        # Clean up old press times (older than timeout)
                                        ctrl_press_times[:] = [t for t in ctrl_press_times if current_time - t < DOUBLE_TAP_TIMEOUT]

                                        # Check if this is a double-tap
                                        if len(ctrl_press_times) > 0:
                                            # DOUBLE-TAP detected!
                                            time_since_last = current_time - ctrl_press_times[-1]
                                            logging.info(f"✓✓ Alt DOUBLE-TAP ({time_since_last:.2f}s) detected")

                                            if recording:
                                                # Stop recording
                                                logging.info("Stopping recording...")
                                                print("\n✓✓ STOP - Transcribing now...")
                                                try:
                                                    stop_recording()
                                                except Exception as e:
                                                    logging.error(f"Exception in stop_recording: {e}")
                                                    import traceback
                                                    traceback.print_exc()
                                            else:
                                                # Start recording
                                                logging.info("Starting recording...")
                                                print("✓ START - Recording... press Alt twice to stop")
                                                start_recording()

                                            # Clear press times to avoid triple-tap
                                            ctrl_press_times.clear()
                                        else:
                                            # First tap
                                            logging.debug(f"Alt pressed - waiting for second tap")
                                            ctrl_press_times.append(current_time)

                        except OSError as e:
                            logging.error(f"Device {device.path} disconnected: {e}")
                            inner_loop_active = False
                            break
                        except Exception as e:
                            logging.error(f"Error reading device {device.path}: {e}")
                            import traceback
                            traceback.print_exc()

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logging.error(f"Error in select/read loop: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Script interrupted by user")
            print("Exiting...")
            break
        except Exception as e:
            logging.error(f"Keyboard listener error: {e}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(2)