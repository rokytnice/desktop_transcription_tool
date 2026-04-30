# Online Transcription Tool 🌐

Spracherkennung mit **Google Cloud Speech-to-Text API**

## Features

- ☁️ **Google Cloud API** (hochwertig, aber mit API Key)
- 🎙️ **Echtzeit-Aufnahme**
- 🇩🇪 **Deutsch Support**
- 📋 **Auto-Einfügen** in aktives Fenster
- ⚡ **Schnelle Transkription**

## Installation

```bash
pip install -r requirements.txt
```

## Vorbereitung

1. **Google Cloud Account** erstellen
2. **Speech-to-Text API** aktivieren
3. **API Key** setzen:
```bash
export API_KEY="dein_google_api_key"
```

## Start

```bash
python transcription_online.py
```

## Bedienung

1. **Ctrl + Alt + Einfg** → Recording startet 🔴
2. **Halten & Sprechen** 🗣️
3. **Loslassen** → Transkribiert & tippt Text ⏹️

## Voraussetzungen

- Google Cloud API Key
- Internet-Verbindung
- Internetquotum beachten!

## Log

Logs: `transcription_listener.log`
