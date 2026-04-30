#!/usr/bin/env python3
"""
Audio File Transcription mit Google Gemini API
Teilt große Audio-Dateien in kleinere Segmente und transkribiert sie mit Gemini.
"""

import os
import sys
from pathlib import Path
from pydub import AudioSegment
import google.generativeai as genai
from typing import List
import time


class AudioTranscriber:
    def __init__(self, api_key: str):
        """
        Initialisiert den Audio-Transcriber mit dem Gemini API Key.

        Args:
            api_key: Der Google Gemini API Key
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY ist nicht gesetzt!")

        genai.configure(api_key=api_key)
        # Verwende gemini-2.5-flash als aktuelles Modell
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def split_audio(self, audio_file: str, chunk_length_ms: int = 60000, output_dir: str = "chunks") -> List[str]:
        """
        Teilt eine große Audio-Datei in kleinere Chunks.

        Args:
            audio_file: Pfad zur Audio-Datei
            chunk_length_ms: Länge jedes Chunks in Millisekunden (Standard: 60 Sekunden)
            output_dir: Verzeichnis für die Audio-Chunks

        Returns:
            Liste der Pfade zu den erstellten Chunk-Dateien
        """
        print(f"Lade Audio-Datei: {audio_file}")

        # Dateierweiterung erkennen
        file_extension = Path(audio_file).suffix.lower()

        # Audio-Datei laden (explizite Format-Angabe für M4A)
        if file_extension == '.m4a':
            audio = AudioSegment.from_file(audio_file, format='m4a')
        else:
            audio = AudioSegment.from_file(audio_file)

        total_length = len(audio)

        print(f"Audio-Länge: {total_length / 1000:.2f} Sekunden")

        # Output-Verzeichnis erstellen
        chunks_dir = Path(output_dir)
        chunks_dir.mkdir(exist_ok=True)

        # Audio in Chunks teilen
        chunk_files = []
        chunk_num = 0

        # Export-Format bestimmen (M4A oder MP3)
        # ffmpeg benötigt 'ipod' als Format für M4A/AAC Container
        if file_extension == '.m4a':
            export_format = 'ipod'
            export_extension = 'm4a'
        else:
            export_format = 'mp3'
            export_extension = 'mp3'

        for i in range(0, total_length, chunk_length_ms):
            chunk = audio[i:i + chunk_length_ms]
            chunk_filename = chunks_dir / f"chunk_{chunk_num:04d}.{export_extension}"

            print(f"Erstelle Chunk {chunk_num + 1}: {chunk_filename}")
            chunk.export(chunk_filename, format=export_format)
            chunk_files.append(str(chunk_filename))
            chunk_num += 1

        print(f"\n{len(chunk_files)} Chunks erstellt")
        return chunk_files

    def transcribe_audio_file(self, audio_file: str) -> str:
        """
        Transkribiert eine einzelne Audio-Datei mit Gemini.

        Args:
            audio_file: Pfad zur Audio-Datei

        Returns:
            Transkribierter Text
        """
        print(f"Transkribiere: {audio_file}")

        try:
            # Audio-Datei hochladen
            uploaded_file = genai.upload_file(audio_file)

            # Warten bis die Datei verarbeitet wurde
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                raise ValueError(f"Fehler beim Verarbeiten der Datei: {audio_file}")

            # Transkription anfordern
            prompt = "Bitte transkribiere diese Audio-Datei vollständig und genau. Gib nur den transkribierten Text zurück, ohne zusätzliche Kommentare."
            response = self.model.generate_content([prompt, uploaded_file])

            # Datei löschen nach Transkription
            genai.delete_file(uploaded_file.name)

            return response.text

        except Exception as e:
            print(f"Fehler bei der Transkription von {audio_file}: {str(e)}")
            return f"[FEHLER beim Transkribieren von {audio_file}]"

    def transcribe_large_audio(self, audio_file: str, chunk_length_seconds: int = 60,
                              output_file: str = "transcription.txt",
                              keep_chunks: bool = False) -> str:
        """
        Transkribiert eine große Audio-Datei, indem sie in Chunks aufgeteilt wird.

        Args:
            audio_file: Pfad zur Audio-Datei
            chunk_length_seconds: Länge jedes Chunks in Sekunden
            output_file: Pfad zur Ausgabedatei für die Transkription
            keep_chunks: Wenn True, werden die Chunk-Dateien nicht gelöscht

        Returns:
            Vollständiger transkribierter Text
        """
        if not os.path.exists(audio_file):
            raise FileNotFoundError(f"Audio-Datei nicht gefunden: {audio_file}")

        # Chunks erstellen
        chunk_length_ms = chunk_length_seconds * 1000
        chunk_files = self.split_audio(audio_file, chunk_length_ms)

        # Alle Chunks transkribieren
        print(f"\nStarte Transkription von {len(chunk_files)} Chunks...")
        all_transcriptions = []

        for idx, chunk_file in enumerate(chunk_files, 1):
            print(f"\n--- Chunk {idx}/{len(chunk_files)} ---")
            transcription = self.transcribe_audio_file(chunk_file)
            all_transcriptions.append(transcription)

            # Kurze Pause zwischen API-Aufrufen
            if idx < len(chunk_files):
                time.sleep(1)

        # Alle Transkriptionen zusammenführen
        full_transcription = "\n\n".join(all_transcriptions)

        # In Datei speichern
        output_path = Path(output_file)
        print(f"\nSpeichere Transkription in: {output_path}")
        output_path.write_text(full_transcription, encoding='utf-8')

        # Chunks löschen falls gewünscht
        if not keep_chunks:
            print("\nLösche temporäre Chunk-Dateien...")
            for chunk_file in chunk_files:
                try:
                    os.remove(chunk_file)
                except Exception as e:
                    print(f"Warnung: Konnte {chunk_file} nicht löschen: {e}")

            # Chunks-Verzeichnis löschen falls leer
            try:
                chunks_dir = Path(chunk_files[0]).parent
                if chunks_dir.exists() and not any(chunks_dir.iterdir()):
                    chunks_dir.rmdir()
            except Exception:
                pass

        print("\n" + "="*50)
        print("Transkription abgeschlossen!")
        print(f"Ausgabedatei: {output_path}")
        print(f"Gesamtlänge: {len(full_transcription)} Zeichen")
        print("="*50)

        return full_transcription


def main():
    """Hauptfunktion für Kommandozeilen-Verwendung"""
    if len(sys.argv) < 2:
        print("Verwendung: python transcribe_audio.py <audio_file> [chunk_length_seconds] [output_file]")
        print("\nBeispiel:")
        print("  python transcribe_audio.py meine_audio.mp3")
        print("  python transcribe_audio.py meine_audio.m4a 30 output.txt")
        sys.exit(1)

    # Parameter auslesen
    audio_file = sys.argv[1]
    chunk_length = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    output_file = sys.argv[3] if len(sys.argv) > 3 else "transcription.txt"

    # API Key aus Umgebungsvariable
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FEHLER: GEMINI_API_KEY Umgebungsvariable ist nicht gesetzt!")
        print("Bitte setzen Sie die Variable:")
        print("  export GEMINI_API_KEY='your-api-key-here'")
        sys.exit(1)

    # Transkription durchführen
    try:
        transcriber = AudioTranscriber(api_key)
        transcriber.transcribe_large_audio(
            audio_file=audio_file,
            chunk_length_seconds=chunk_length,
            output_file=output_file,
            keep_chunks=False
        )
    except Exception as e:
        print(f"\nFEHLER: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
