# Autostart Setup für Desktop Transcription Tool

Diese Anleitung erklärt, wie du den Transcription Tool so einrichtest, dass er automatisch beim Systemstart gestartet wird.

## Schnellstart

```bash
chmod +x setup-autostart.sh
./setup-autostart.sh
```

Das Skript wird:
1. Die Abhängigkeiten installieren (falls noch nicht geschehen)
2. Einen systemd User-Service erstellen
3. Den Service für Autostart aktivieren
4. Optional den Service sofort starten

## Manuelle Installation

Falls du die manuelle Einrichtung bevorzugst:

### 1. Installation durchführen
```bash
cd offline
./install.sh
cd ..
```

### 2. Service-Datei erstellen
```bash
mkdir -p ~/.config/systemd/user
cp transcription-offline.service ~/.config/systemd/user/
# Pfade in der Datei anpassen (HOME-Verzeichnis)
```

### 3. Service aktivieren
```bash
systemctl --user daemon-reload
systemctl --user enable transcription-offline.service
systemctl --user start transcription-offline.service
```

## Verwendung

### Service starten/stoppen
```bash
# Starten
systemctl --user start transcription-offline

# Stoppen
systemctl --user stop transcription-offline

# Status anschauen
systemctl --user status transcription-offline
```

### Logs ansehen
```bash
# Live-Logs verfolgen
journalctl --user -u transcription-offline -f

# Letzte 50 Zeilen
journalctl --user -u transcription-offline -n 50

# Fehler anschauen
journalctl --user -u transcription-offline -p err
```

### Autostart deaktivieren
```bash
systemctl --user disable transcription-offline.service
systemctl --user stop transcription-offline.service
```

## Systemanforderungen

- Linux (Ubuntu, Debian, Fedora, etc.)
- systemd
- Python 3.12+
- Mikrofon und Audio-Eingabegerät
- X11/Wayland mit DISPLAY Variable

## Fehlerbehebung

### Service startet nicht
```bash
journalctl --user -u transcription-offline -n 100
```
Überprüfe die Logs auf Fehler.

### Keine Tastaturerkennung
Der Service läuft im Hintergrund. Stelle sicher, dass:
- Der User in der `input` Gruppe ist: `groups | grep input`
- Falls nicht: `sudo usermod -a -G input $USER` (dann neuen Login)

### Audio-Probleme
```bash
# Verfügbare Geräte anschauen
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

## Logs
Service-Logs werden in systemd journal gespeichert:
```bash
journalctl --user -u transcription-offline
```

Zusätzliche Logs im Projektverzeichnis:
- `offline/transcription_listener.log`
- `offline/audio_recording.wav`

## Sicherheit

Der Service läuft mit deinem User-Account (nicht root). Er braucht:
- Zugriff auf Eingabegeräte (evdev)
- Zugriff auf Audio-Geräte (sounddevice)
- X11/Wayland Zugriff (für Clipboard)

Diese Berechtigungen werden durch deine User-Gruppen kontrolliert.
