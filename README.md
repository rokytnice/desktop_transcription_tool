# Desktop Transcription Tool 🎤

Mehrere Spracherkennungs-Tools für verschiedene Anwendungsfälle.

## 📁 Projektstruktur

```
desktop_transcription_tool/
├── offline/                    🎤 Offline Transkription (Whisper)
│   ├── transcription_offline.py
│   ├── install.sh
│   ├── run.sh
│   ├── requirements.txt
│   └── README.md
│
├── online/                     🌐 Online Transkription (Google API)
│   ├── transcription_online.py
│   ├── requirements.txt
│   └── README.md
│
├── text_improvement/           ✨ Text-Verbesserung mit LLM
│   ├── transcription_listener_offline_text_improvement.py
│   └── transcription_listener_offline_text_improvement.md
│
├── big_audio_file_transcription/ 📁 Große Audio-Dateien
│   ├── transcribe_audio.py
│   ├── requirements.txt
│   └── chunks/
│
├── docs/                       📚 Dokumentation
│   ├── README.md
│   └── functional_requirements.md
│
└── README.md                   (dieses File)
```

## 🚀 Schnelstart

### Offline (Whisper - lokal, kein API Key nötig)
```bash
cd offline
./install.sh
./run.sh
```

### Online (Google Speech API - mit API Key)
```bash
cd online
pip install -r requirements.txt
export API_KEY="your_google_api_key"
python transcription_online.py
```

## 🛠️ Features nach Tool

| Tool | Features | Anforderungen |
|------|----------|---------------|
| **Offline** | 🎙️ Echtzeit, 🤖 Whisper, 🇩🇪 Deutsch, 📋 Clipboard | Python 3.12, xclip |
| **Online** | ☁️ Google API, 🎙️ Mikrofon, 📝 Auto-Type | API Key, Internet |
| **Text Improvement** | ✨ LLM-basierte Verbesserung | Google Gemini API |

## 📋 Bedienung (Offline)

1. **Alt Tap Tap** → Recording startet 🔴
2. **Sprechen Sie 2-3 Sekunden** 🗣️
3. **Alt Tap Tap** → Recording stoppt & transkribiert ⏹️
4. **Ctrl+V** → Text einfügen 📝

## 📖 Dokumentation

- [Offline Transkription](offline/README.md)
- [Online Transkription](online/README.md)
- [Anforderungen](docs/functional_requirements.md)

## 🔧 System-Anforderungen

- Python 3.12+
- Linux (getestet auf Ubuntu 24.04)
- Audio-Geräte (Mikrofon)
- xclip (für Clipboard-Funktion)

## 📝 Logs

Logs werden gespeichert in: `transcription_listener.log`

## 🤝 Beitrag

Fragen oder Probleme? GitHub Issues willkommen!

---

*Made with ❤️ for transcription automation*
