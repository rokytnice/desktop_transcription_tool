# Datei: talk_analyzer.py

import soundcard as sc
import numpy as np
import whisper
import threading
import tempfile
import wave
import os
import time
from queue import Queue
import google.generativeai as genai

class SpeakerTranscriber:
    """
    Eine Klasse, die den Audio-Output der Lautsprecher in Echtzeit abhört,
    Pausen erkennt, das Audio transkribiert und eine Antwort von einem LLM generiert.
    """

    def __init__(self, model_size="base", lang="de", pause_seconds=1.0, silence_threshold=0.01,
                 llm_model_name="gemini-1.5-flash-latest"):
        """
        Initialisiert den Transkribierer.

        :param model_size: Die Größe des Whisper-Modells (z.B. "tiny", "base", "small").
        :param lang: Die erwartete Sprache des Audios (z.B. "de" für Deutsch).
        :param pause_seconds: Die Dauer der Stille in Sekunden, die eine Verarbeitung auslöst.
        :param silence_threshold: Der Lautstärke-Schwellenwert, unter dem Audio als "still" gilt.
        :param llm_model_name: Der Standard-Name des Google Gemini-Modells.
        """
        self.pause_threshold = pause_seconds
        self.silence_threshold = silence_threshold
        self.language = lang
        self.sample_rate = 16000  # Whisper wurde mit 16kHz trainiert

        # Eine Queue, um die Ergebnisse (Transkription, LLM-Antwort) sicher aus dem Thread zu erhalten
        self.result_queue = Queue()

        print("[INFO] Lade das Whisper-Modell...")
        self.model = whisper.load_model(model_size)
        print(f"[INFO] Whisper-Modell '{model_size}' erfolgreich geladen.")

        # GEÄNDERT: Initialisierung des Google LLM mit Unterstützung für Umgebungsvariable
        self.llm_model = None
        # Priorität: Umgebungsvariable GOOGLE_LLM > Parameter llm_model_name
        final_llm_model_name = os.getenv("GOOGLE_LLM", llm_model_name)

        print("[INFO] Konfiguriere Google LLM...")
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Die Umgebungsvariable GEMINI_API_KEY wurde nicht gefunden. LLM-Funktionalität ist deaktiviert.")
            genai.configure(api_key=api_key)
            self.llm_model = genai.GenerativeModel(final_llm_model_name)
            print(f"[INFO] Google LLM '{final_llm_model_name}' erfolgreich konfiguriert.")
        except Exception as e:
            print(f"[FEHLER] Fehler bei der Initialisierung des Google LLM: {e}")

        self.audio_buffer = []
        self.silence_start_time = None
        self.is_speaking = False

    def _process_audio_and_query_llm(self, audio_data):
        """
        Wird in einem separaten Thread ausgeführt, um die Aufnahme nicht zu blockieren.
        Transkribiert das Audio und sendet das Ergebnis an das LLM.
        """
        transcribed_text = ""
        temp_path = None
        try:
            # Erstelle eine temporäre WAV-Datei für Whisper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                temp_path = tmp_wav.name
                with wave.open(tmp_wav, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    int16_data = (audio_data * 32767).astype(np.int16)
                    wf.writeframes(int16_data.tobytes())

            # Führe die Transkription durch
            result = self.model.transcribe(temp_path, language=self.language, fp16=False)
            transcribed_text = result['text'].strip()

            if transcribed_text:
                # Sende den transkribierten Text an das LLM, falls es konfiguriert ist
                llm_response = "[LLM Deaktiviert oder Fehler bei Initialisierung]"
                if self.llm_model:
                    print(f"[STATUS] Sende '{transcribed_text}' an das LLM...")
                    try:
                        # Hier kann der Prompt angepasst werden, um das Verhalten des LLM zu steuern.
                        prompt = f"finde heraus worum es in dem folgenden text geht und erkläre due technischen hintegründe kurz und knapp: '{transcribed_text}'"
                        response = self.llm_model.generate_content(prompt)
                        llm_response = response.text.strip()
                    except Exception as e:
                        llm_response = f"[LLM-FEHLER: {e}]"

                # Lege das Ergebnis-Tupel in die Queue
                self.result_queue.put((transcribed_text, llm_response))

        except Exception as e:
            print(f"[FEHLER] Fehler bei der Verarbeitung: {e}")
            if transcribed_text:  # Falls Transkription klappte, aber LLM nicht
                self.result_queue.put((transcribed_text, f"[Verarbeitungsfehler: {e}]"))
        finally:
            # Lösche die temporäre Datei
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def listen(self):
        """Startet den Hauptprozess des Zuhörens und der Pausenerkennung."""
        try:
            default_speaker = sc.default_speaker()
            print(f"[INFO] Lausche auf Lautsprecher: '{default_speaker.name}' (Loopback)")
            mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
        except Exception:
            print("\n[FEHLER] Konnte kein Loopback-Aufnahmegerät finden.")
            print("Stelle sicher, dass dein Betriebssystem und deine Sound-Treiber dies unterstützen.")
            return

        print("\n[INFO] Zuhören gestartet... (Beenden mit Strg+C)")
        print("-" * 50)

        with mic.recorder(samplerate=self.sample_rate, channels=1) as recorder:
            while True:
                try:
                    data = recorder.record(numframes=1024)
                    rms = np.sqrt(np.mean(data ** 2))

                    if rms > self.silence_threshold:
                        if not self.is_speaking:
                            print("[STATUS] Sprache erkannt...")
                            self.is_speaking = True
                        self.audio_buffer.append(data)
                        self.silence_start_time = None
                    else:
                        if self.is_speaking:
                            if self.silence_start_time is None:
                                self.silence_start_time = time.time()

                            if (time.time() - self.silence_start_time > self.pause_threshold):
                                print(f"[STATUS] Pause von {self.pause_threshold}s erkannt. Starte Verarbeitung...")
                                audio_to_process = np.concatenate(self.audio_buffer)

                                # Starte die Verarbeitung (Transkription + LLM) in einem neuen Thread
                                t = threading.Thread(target=self._process_audio_and_query_llm, args=(audio_to_process,))
                                t.start()

                                # Zustand zurücksetzen
                                self.audio_buffer.clear()
                                self.is_speaking = False
                                self.silence_start_time = None

                    # Prüfe, ob ein neues Ergebnis (Transkription + LLM-Antwort) fertig ist
                    if not self.result_queue.empty():
                        original_text, llm_answer = self.result_queue.get()

                        # Formatierte Ausgabe
                        print("\n" + "=" * 50)
                        print(f"🗣️  Ihre Sprache: {original_text}")
                        print(f"🤖 Gemini Antwort: {llm_answer}")
                        print("=" * 50)
                        print("\n[STATUS] Lausche erneut...")

                except KeyboardInterrupt:
                    print("\n[INFO] Programm wird beendet.")
                    break
                except Exception as e:
                    print(f"[FEHLER] Ein unerwarteter Fehler ist aufgetreten: {e}")
                    break


if __name__ == "__main__":
    transcriber = SpeakerTranscriber(
        model_size="base",          # Whisper-Modell: "tiny", "base", "small", "medium", "large"
        lang="de",                  # Sprache des Audios
        pause_seconds=1.5,          # Dauer der Stille, die eine Verarbeitung auslöst
        silence_threshold=0.008,    # Empfindlichkeit für Stille (kleiner = empfindlicher)
        # Der Modellname kann hier oder über die Umgebungsvariable GOOGLE_LLM gesetzt werden
        llm_model_name="gemini-1.5-flash-latest"
    )
    transcriber.listen()