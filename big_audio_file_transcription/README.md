# Audio Transkription mit Google Gemini

Dieses Programm transkribiert große Audio-Dateien mithilfe der Google Gemini API. Die Audio-Datei wird automatisch in kleinere Segmente aufgeteilt, jedes Segment wird transkribiert, und alle Transkriptionen werden in einer einzigen Ausgabedatei zusammengeführt.

## Voraussetzungen

- Python 3.7 oder höher
- Google Gemini API Key
- FFmpeg (für Audio-Verarbeitung)

### FFmpeg Installation

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Laden Sie FFmpeg von https://ffmpeg.org/download.html herunter und fügen Sie es zu Ihrem PATH hinzu.

## Installation

1. Klonen oder navigieren Sie zum Projektverzeichnis:
```bash
cd big_audio_file_transcription
```

2. Installieren Sie die erforderlichen Python-Pakete:
```bash
pip install -r requirements.txt
```

3. Setzen Sie Ihren Gemini API Key als Umgebungsvariable:
```bash
export GEMINI_API_KEY='ihr-api-key-hier'
```

Um den API Key dauerhaft zu setzen, fügen Sie die Zeile zu Ihrer `~/.bashrc` oder `~/.zshrc` hinzu.

## Verwendung

### Grundlegende Verwendung

```bash
python transcribe_audio.py <audio_datei>
```

Beispiel:
```bash
python transcribe_audio.py meine_audio.mp3
```

Dies wird:
- Die Audio-Datei in 60-Sekunden-Chunks aufteilen
- Jeden Chunk mit Gemini transkribieren
- Die vollständige Transkription in `transcription.txt` speichern

### Erweiterte Optionen

```bash
python transcribe_audio.py <audio_datei> <chunk_länge_in_sekunden> <ausgabe_datei>
```

Beispiel mit 30-Sekunden-Chunks und benutzerdefinierter Ausgabedatei:
```bash
python transcribe_audio.py interview.mp3 30 interview_transkription.txt
```

### Als Python-Modul verwenden

```python
from transcribe_audio import AudioTranscriber
import os

# API Key aus Umgebungsvariable
api_key = os.getenv("GEMINI_API_KEY")

# Transcriber erstellen
transcriber = AudioTranscriber(api_key)

# Audio transkribieren
transcription = transcriber.transcribe_large_audio(
    audio_file="meine_audio.mp3",
    chunk_length_seconds=60,
    output_file="output.txt",
    keep_chunks=False  # Chunks nach Transkription löschen
)

print(transcription)
```

## Funktionsweise

1. **Audio-Splitting**: Die große Audio-Datei wird in kleinere Chunks aufgeteilt (Standard: 60 Sekunden)
2. **Upload & Transkription**: Jeder Chunk wird zur Gemini API hochgeladen und transkribiert
3. **Zusammenführung**: Alle Transkriptionen werden zu einem vollständigen Text zusammengeführt
4. **Speicherung**: Der vollständige Text wird in einer Datei gespeichert
5. **Aufräumen**: Temporäre Chunk-Dateien werden automatisch gelöscht

## Unterstützte Audio-Formate

Das Programm unterstützt alle von FFmpeg unterstützten Audio-Formate, einschließlich:
- MP3
- WAV
- M4A
- FLAC
- OGG
- AAC

## Tipps

- **Chunk-Länge**: Für bessere Ergebnisse bei längeren Dateien verwenden Sie kürzere Chunks (30-60 Sekunden)
- **API-Limits**: Beachten Sie die Rate Limits der Gemini API bei sehr großen Dateien
- **Speicherplatz**: Stellen Sie sicher, dass genügend Speicherplatz für temporäre Chunks vorhanden ist

## Fehlerbehebung

**"GEMINI_API_KEY Umgebungsvariable ist nicht gesetzt"**
- Stellen Sie sicher, dass Sie den API Key korrekt exportiert haben
- Überprüfen Sie mit: `echo $GEMINI_API_KEY`

**"ffmpeg not found" oder ähnliche Fehler**
- Installieren Sie FFmpeg wie oben beschrieben
- Überprüfen Sie die Installation mit: `ffmpeg -version`

**API-Fehler**
- Überprüfen Sie, ob Ihr API Key gültig ist
- Stellen Sie sicher, dass Sie Zugriff auf die Gemini API haben
- Prüfen Sie Ihre API-Quota

## Lizenz

Dieses Projekt ist für den persönlichen und kommerziellen Gebrauch frei verfügbar.
