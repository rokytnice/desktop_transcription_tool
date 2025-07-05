# Datei: talk_analyzer_google_cloud.py

import soundcard as sc
import numpy as np
from google.cloud import speech
import threading
import os
import time
from queue import Queue, Empty
import google.generativeai as genai
from pynput import keyboard
import colorama
from colorama import Fore, Style
from google.api_core.exceptions import GoogleAPICallError
import logging
# NEUER IMPORT für die API-Schlüssel-Authentifizierung bei GCP-Diensten
from google.api_core.client_options import ClientOptions

# Bessere Lesbarkeit durch Konstanten
SOURCE_MICROPHONE = "Mikrofon"
SOURCE_SPEAKER = "Lautsprecher"

# Konfiguration des Loggings für bessere Übersicht in Multi-Threading-Umgebungen
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class RealtimeTalkAnalyzer:
    """
    Eine Klasse, die Audio von Lautsprecher und Mikrofon GLEICHZEITIG
    in Echtzeit abhört, Pausen erkennt (automatisch oder manuell per Strg-Doppelklick),
    dieses mit Google Cloud Speech-to-Text transkribiert und eine Antwort
    von einem LLM generiert.
    """

    def __init__(self, lang="de",
                 speaker_pause_seconds=2.0, mic_pause_seconds=1.5,
                 silence_threshold=0.01, llm_model_name="gemini-1.5-flash-latest",
                 double_press_threshold=0.4, num_workers=2,
                 prompt_template="Wir befinden uns im Kontext der Softwareentwicklung. Finde heraus, worum es in dem folgenden Text geht, und erkläre den Begriff, die Definition und die fachliche Relevanz kurz und knapp: '{text}'"):
        """Initialisiert den Analyzer."""
        # Konfigurationen
        self.speaker_pause_threshold = speaker_pause_seconds
        self.mic_pause_threshold = mic_pause_seconds
        self.silence_threshold = silence_threshold
        self.language = lang
        self.sample_rate = 16000
        self.double_press_threshold = double_press_threshold
        self.prompt_template = prompt_template
        self.num_workers = num_workers

        # Threading und Queues
        self.processing_queue = Queue()
        self.result_queue = Queue()
        self.stop_event = threading.Event()
        self.manual_process_event = threading.Event()
        self.last_ctrl_press_time = 0
        self.threads = []

        # Client-Initialisierung
        self.speech_client = self._initialize_speech_client()
        self.llm_model = self._initialize_llm(llm_model_name)

    def _initialize_speech_client(self):
        """
        Initialisiert den Google Speech Client mit einem API-Schlüssel.
        HINWEIS: Dies ist NICHT die empfohlene Methode. Sie erfordert, dass der
        API-Schlüssel in der Google Cloud Console für die Speech-to-Text API
        aktiviert ist.
        """
        logging.info("Initialisiere Google Cloud Speech-to-Text Client (mit API-Schlüssel)...")
        try:
            # Versuche, denselben API-Schlüssel wie für Gemini zu verwenden
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Die Umgebungsvariable 'GEMINI_API_KEY' wurde nicht gefunden und wird für Speech-to-Text benötigt.")

            # Konfiguriere den Client mit dem API-Schlüssel
            client_options = ClientOptions(api_key=api_key)
            client = speech.SpeechClient(client_options=client_options)

            logging.info("Google Speech-to-Text Client erfolgreich initialisiert.")
            return client
        except Exception as e:
            logging.error(
                f"Konnte Google Speech Client nicht initialisieren. Ist 'GEMINI_API_KEY' gesetzt und für die Speech-to-Text API freigegeben? Fehler: {e}")
            return None

    def _initialize_llm(self, model_name):
        """Initialisiert und gibt das Generative AI Model zurück."""
        final_model_name = os.getenv("GOOGLE_LLM", model_name)
        logging.info(f"Konfiguriere Google LLM '{final_model_name}'...")
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Die Umgebungsvariable GEMINI_API_KEY wurde nicht gefunden.")
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(final_model_name)
            logging.info(f"Google LLM '{final_model_name}' erfolgreich konfiguriert.")
            return model
        except Exception as e:
            logging.error(f"Fehler bei der Initialisierung des Google LLM: {e}")
            return None

    def _transcribe_audio(self, audio_data: np.ndarray) -> str | None:
        """Sendet Audiodaten an die Google Speech API und gibt den Text zurück."""
        if not self.speech_client:
            logging.warning("Transkription übersprungen, da der Speech-Client nicht verfügbar ist.")
            return None
        try:
            int16_data = (audio_data * 32767).astype(np.int16)
            audio_content = int16_data.tobytes()

            recognition_audio = speech.RecognitionAudio(content=audio_content)
            recognition_config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=self.sample_rate,
                language_code=self.language,
                enable_automatic_punctuation=True,
            )

            logging.info("Sende Audio an Google Speech-to-Text...")
            response = self.speech_client.recognize(config=recognition_config, audio=recognition_audio)

            results = [res.alternatives[0].transcript for res in response.results]
            return " ".join(results).strip()
        except GoogleAPICallError as e:
            logging.error(f"API-Fehler bei der Transkription: {e}")
        except Exception as e:
            logging.error(f"Unerwarteter Fehler bei der Transkription: {e}")
        return None

    # ... (der Rest der Klasse bleibt unverändert) ...

    def _query_llm(self, text: str) -> str:
        """Fragt das LLM mit dem transkribierten Text an."""
        if not self.llm_model:
            return "[LLM nicht verfügbar]"

        logging.info("Sende Text an das LLM...")
        try:
            prompt = self.prompt_template.format(text=text)
            response = self.llm_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logging.error(f"Fehler bei der LLM-Anfrage: {e}")
            return f"[LLM-FEHLER: {e}]"

    def _processing_worker(self):
        """
        Worker-Funktion, die kontinuierlich Aufgaben aus der Queue verarbeitet.
        Dies ist effizienter als das Erstellen eines neuen Threads pro Aufgabe.
        """
        while not self.stop_event.is_set():
            try:
                audio_data, source_name = self.processing_queue.get(timeout=1)

                logging.info(f"Verarbeite Audio von '{source_name}'...")
                transcribed_text = self._transcribe_audio(audio_data)

                if transcribed_text:
                    llm_response = self._query_llm(transcribed_text)
                    self.result_queue.put((source_name, transcribed_text, llm_response))
                else:
                    logging.info(f"Kein Text von '{source_name}' erkannt.")

                self.processing_queue.task_done()
            except Empty:
                continue

    def _listen_to_source(self, source_type: str):
        """Die Kern-Logik des Zuhörens für eine Audioquelle."""
        recorder_device, pause_threshold, source_name = None, 0, ""
        try:
            if source_type == "microphone":
                recorder_device = sc.default_microphone()
                pause_threshold = self.mic_pause_threshold
                source_name = SOURCE_MICROPHONE
            else:
                default_speaker = sc.default_speaker()
                recorder_device = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
                pause_threshold = self.speaker_pause_threshold
                source_name = SOURCE_SPEAKER
            logging.info(f"Lausche auf {source_name}: '{recorder_device.name}'")
        except Exception as e:
            logging.error(f"Konnte Quelle '{source_name}' nicht starten: {e}. Dieser Thread wird beendet.")
            return

        audio_buffer, silence_start_time, is_speaking = [], None, False
        with recorder_device.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            while not self.stop_event.is_set():
                data = recorder.record(numframes=1024)
                if data is None or data.size == 0: continue

                is_loud_enough = np.sqrt(np.mean(data ** 2)) > self.silence_threshold
                if is_loud_enough:
                    if not is_speaking: is_speaking = True
                    audio_buffer.append(data)
                    silence_start_time = None
                elif is_speaking:
                    if silence_start_time is None: silence_start_time = time.time()

                manual_trigger = self.manual_process_event.is_set()
                automatic_trigger = is_speaking and silence_start_time and (
                            time.time() - silence_start_time > pause_threshold)

                if is_speaking and audio_buffer and (manual_trigger or automatic_trigger):
                    if manual_trigger:
                        logging.info(f"Manuelle Verarbeitung für '{source_name}' ausgelöst.")
                        self.manual_process_event.clear()
                    else:
                        logging.info(f"Automatische Pause für '{source_name}' erkannt.")

                    # Audio in die Verarbeitungs-Queue legen, anstatt einen neuen Thread zu starten
                    self.processing_queue.put((np.concatenate(audio_buffer), source_name))
                    audio_buffer.clear()
                    is_speaking = False
                    silence_start_time = None

    def _handle_user_input(self):
        """Wartet auf einen doppelten Druck der Strg-Taste."""
        logging.info("Drücke zweimal schnell die [Strg]-Taste, um die Aufnahme manuell zu verarbeiten.")

        def on_press(key):
            if self.stop_event.is_set(): return False
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]:
                current_time = time.time()
                if current_time - self.last_ctrl_press_time < self.double_press_threshold:
                    logging.info("Doppelter Strg-Druck erkannt. Verarbeitung wird ausgelöst...")
                    self.manual_process_event.set()
                self.last_ctrl_press_time = current_time

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()

    def start(self):
        """Startet alle Threads und beginnt mit der Verarbeitung."""
        if not self.speech_client or not self.llm_model:
            logging.critical(
                "Programm kann nicht gestartet werden, da ein oder mehrere Clients nicht initialisiert werden konnten.")
            return

        # Worker-Threads starten
        for i in range(self.num_workers):
            worker = threading.Thread(target=self._processing_worker, name=f"Worker-{i + 1}", daemon=True)
            worker.start()
            self.threads.append(worker)

        # Listener-Threads starten
        mic_thread = threading.Thread(target=self._listen_to_source, args=("microphone",), name="MicListener",
                                      daemon=True)
        speaker_thread = threading.Thread(target=self._listen_to_source, args=("speaker",), name="SpeakerListener",
                                          daemon=True)
        input_thread = threading.Thread(target=self._handle_user_input, name="InputHandler", daemon=True)

        self.threads.extend([mic_thread, speaker_thread, input_thread])
        mic_thread.start()
        speaker_thread.start()
        input_thread.start()

        logging.info("Alle Systeme sind aktiv. (Beenden mit Strg+C)")
        print("-" * 50)

        source_icons = {SOURCE_MICROPHONE: "🎤", SOURCE_SPEAKER: "🔊"}
        try:
            while not self.stop_event.is_set():
                try:
                    source_name, original_text, llm_answer = self.result_queue.get(timeout=1)
                    icon = source_icons.get(source_name, "🗣️")
                    print("\n" + "=" * 50)
                    print(f"{icon} Quelle: {source_name}")
                    print(f"   Erkannter Text: {original_text}")
                    print(f"🤖 Gemini Antwort: {Fore.CYAN}{llm_answer}{Style.RESET_ALL}")
                    print("=" * 50)
                except Empty:
                    continue
        except KeyboardInterrupt:
            logging.info("Programm wird beendet. Warte auf Threads...")
            self.stop_event.set()
            # Warten, bis alle Threads sauber beendet sind
            for thread in self.threads:
                thread.join(timeout=2)
            logging.info("Alle Threads beendet. Auf Wiedersehen!")


if __name__ == "__main__":
    colorama.init()
    analyzer = RealtimeTalkAnalyzer(
        lang="de",
        speaker_pause_seconds=2.5,
        mic_pause_seconds=1.5,
        silence_threshold=0.008,
        double_press_threshold=0.4,
        num_workers=2
    )
    analyzer.start()