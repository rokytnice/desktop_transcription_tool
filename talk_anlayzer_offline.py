# Datei: talk_analyzer.py

import soundcard as sc
import numpy as np
import whisper
import threading
import tempfile
import wave
import os
import time
from queue import Queue, Empty
import google.generativeai as genai
from pynput import keyboard
# NEU: Bibliothek für farbige Terminal-Ausgaben
import colorama
from colorama import Fore, Style


class SpeakerTranscriber:
    """
    Eine Klasse, die Audio von Lautsprecher und Mikrofon GLEICHZEITIG
    in Echtzeit abhört, Pausen erkennt (automatisch oder manuell per Strg-Doppelklick)
    und eine Antwort von einem LLM generiert.
    """

    def __init__(self, model_size="base", lang="de",
                 speaker_pause_seconds=2.0, mic_pause_seconds=1.5,
                 silence_threshold=0.01, llm_model_name="gemini-1.5-flash-latest",
                 double_press_threshold=0.4):
        """
        Initialisiert den Transkribierer.
        """
        self.speaker_pause_threshold = speaker_pause_seconds
        self.mic_pause_threshold = mic_pause_seconds
        self.silence_threshold = silence_threshold
        self.language = lang
        self.sample_rate = 16000

        self.result_queue = Queue()
        self.stop_event = threading.Event()
        self.manual_process_event = threading.Event()

        self.double_press_threshold = double_press_threshold
        self.last_ctrl_press_time = 0

        print("[INFO] Lade das Whisper-Modell...")
        self.model = whisper.load_model(model_size)
        print(f"[INFO] Whisper-Modell '{model_size}' erfolgreich geladen.")

        self.llm_model = None
        final_llm_model_name = os.getenv("GOOGLE_LLM", llm_model_name)

        print("[INFO] Konfiguriere Google LLM...")
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Die Umgebungsvariable GEMINI_API_KEY wurde nicht gefunden.")
            genai.configure(api_key=api_key)
            self.llm_model = genai.GenerativeModel(final_llm_model_name)
            print(f"[INFO] Google LLM '{final_llm_model_name}' erfolgreich konfiguriert.")
        except Exception as e:
            print(f"[FEHLER] Fehler bei der Initialisierung des Google LLM: {e}")

    def _process_audio_and_query_llm(self, audio_data, source_name: str):
        """
        Transkribiert Audio und fragt das LLM an. Läuft in einem eigenen Thread.
        """
        transcribed_text = ""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                temp_path = tmp_wav.name
                with wave.open(tmp_wav, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    int16_data = (audio_data * 32767).astype(np.int16)
                    wf.writeframes(int16_data.tobytes())

            result = self.model.transcribe(temp_path, language=self.language, fp16=False)
            transcribed_text = result['text'].strip()

            if transcribed_text:
                llm_response = "[LLM Deaktiviert oder Fehler]"
                if self.llm_model:
                    print(f"[STATUS] Sende Text von '{source_name}' an das LLM...")
                    try:
                        prompt = f"wir befinden uns im Kontext der softwareentwicklung. finde heraus worum es in dem folgenden text geht und erkläre den begriff, die definition und fachliche relevanz kurz und knapp: '{transcribed_text}'"
                        response = self.llm_model.generate_content(prompt)
                        llm_response = response.text.strip()
                    except Exception as e:
                        llm_response = f"[LLM-FEHLER: {e}]"

                self.result_queue.put((source_name, transcribed_text, llm_response))

        except Exception as e:
            print(f"[FEHLER] Fehler bei der Verarbeitung von '{source_name}': {e}")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _listen_to_source(self, source_type: str):
        """
        Die Kern-Logik des Zuhörens, die für jede Quelle in einem separaten Thread läuft.
        """
        recorder_device = None
        pause_threshold = 0
        source_name = ""

        try:
            if source_type == "microphone":
                recorder_device = sc.default_microphone()
                pause_threshold = self.mic_pause_threshold
                source_name = "Mikrofon"
                print(f"[INFO] Lausche auf Mikrofon: '{recorder_device.name}'")
            else:  # 'speaker'
                default_speaker = sc.default_speaker()
                recorder_device = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
                pause_threshold = self.speaker_pause_threshold
                source_name = "Lautsprecher"
                print(f"[INFO] Lausche auf Lautsprecher: '{default_speaker.name}' (Loopback)")
        except Exception as e:
            print(f"\n[FEHLER] Konnte Quelle '{source_type}' nicht starten: {e}. Dieser Thread wird beendet.")
            return

        audio_buffer = []
        silence_start_time = None
        is_speaking = False

        with recorder_device.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            while not self.stop_event.is_set():
                data = recorder.record(numframes=1024)
                rms = np.sqrt(np.mean(data ** 2))

                if rms > self.silence_threshold:
                    if not is_speaking:
                        is_speaking = True
                    audio_buffer.append(data)
                    silence_start_time = None
                else:
                    if is_speaking and silence_start_time is None:
                        silence_start_time = time.time()

                manual_trigger = self.manual_process_event.is_set()
                automatic_trigger = is_speaking and silence_start_time and (
                            time.time() - silence_start_time > pause_threshold)

                if is_speaking and audio_buffer and (manual_trigger or automatic_trigger):
                    if manual_trigger:
                        print(f"[STATUS] Manuelle Verarbeitung für '{source_name}' ausgelöst.")
                        self.manual_process_event.clear()
                    else:
                        print(f"[STATUS] Automatische Pause für '{source_name}' erkannt.")

                    audio_to_process = np.concatenate(audio_buffer)
                    t = threading.Thread(target=self._process_audio_and_query_llm, args=(audio_to_process, source_name))
                    t.start()

                    audio_buffer.clear()
                    is_speaking = False
                    silence_start_time = None

    def _handle_user_input(self):
        """Wartet in einem separaten Thread auf einen doppelten Druck der Strg-Taste."""
        print("\n[AKTION] Drücke zweimal schnell die [Strg]-Taste, um die Aufnahme manuell zu verarbeiten.")

        def on_press(key):
            if self.stop_event.is_set():
                return False

            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
                current_time = time.time()
                if current_time - self.last_ctrl_press_time < self.double_press_threshold:
                    print("[AKTION] Doppelter Strg-Druck erkannt. Verarbeitung wird ausgelöst...")
                    self.manual_process_event.set()
                self.last_ctrl_press_time = current_time

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()

    def start_listening(self):
        """
        Startet die Listener-Threads und verarbeitet die Ergebnisse aus der Queue.
        """
        mic_thread = threading.Thread(target=self._listen_to_source, args=("microphone",), daemon=True)
        speaker_thread = threading.Thread(target=self._listen_to_source, args=("speaker",), daemon=True)
        input_thread = threading.Thread(target=self._handle_user_input, daemon=True)

        mic_thread.start()
        speaker_thread.start()
        input_thread.start()

        print("\n[INFO] Beide Quellen sind aktiv. (Beenden mit Strg+C)")
        print("-" * 50)

        source_icons = {"Mikrofon": "🎤", "Lautsprecher": "🔊"}

        try:
            while True:
                try:
                    source_name, original_text, llm_answer = self.result_queue.get(timeout=1)
                    icon = source_icons.get(source_name, "🗣️")
                    print("\n" + "=" * 50)
                    print(f"{icon} Quelle: {source_name}")
                    print(f"   Erkannter Text: {original_text}")
                    # GEÄNDERT: Füge Farbe zur LLM-Antwort hinzu
                    print(f"🤖 Gemini Antwort: {Fore.CYAN}{llm_answer}{Style.RESET_ALL}")
                    print("=" * 50)
                except Empty:
                    continue
        except KeyboardInterrupt:
            print("\n[INFO] Programm wird beendet.")
            self.stop_event.set()


if __name__ == "__main__":
    # NEU: Initialisiere colorama für plattformübergreifende Farben
    colorama.init()

    transcriber = SpeakerTranscriber(
        model_size="base",
        lang="de",
        speaker_pause_seconds=2.5,
        mic_pause_seconds=1.5,
        silence_threshold=0.008,
        double_press_threshold=0.4
    )
    transcriber.start_listening()