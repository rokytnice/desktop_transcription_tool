# Changelog

Alle wichtigen Änderungen werden in dieser Datei dokumentiert.

## [1.7.0] - 2026-06-24

### Added
- **`setup-service.sh`** — flexibles Service-Setup mit **Autostart bei Rechnerstart**
  - Modus wählbar: `faster-streaming` (Standard), `streaming`, `offline`
  - Optionen `--model`, `--device`, `--no-start`
  - Erzeugt eine **modus-spezifische** systemd-User-Unit **dynamisch**
    (`transcription-faster-streaming.service` / `transcription-streaming.service`
    / `transcription-offline.service`) — Repo-Pfad, venv, `XDG_RUNTIME_DIR`,
    `WAYLAND_DISPLAY` werden automatisch erkannt, nichts hartkodiert
  - Beim Einrichten eines Modus werden alle anderen Modus-Units sauber
    abgeschaltet/entfernt, sodass nie zwei Services gleichzeitig tippen
  - Aktiviert `loginctl enable-linger` (User-Manager startet bei Boot) und bindet
    die Unit an `graphical-session.target` (Start, sobald die Wayland-Sitzung steht)
  - Installiert/aktualisiert die globalen Kommandos `transcription-{start,stop,
    restart,status,log}`

### Changed
- `install.sh` delegiert die Service-Einrichtung jetzt an `setup-service.sh`
  (Modus per `TRANSCRIPTION_MODE=…` überschreibbar; Standard `faster-streaming`)
- `enable-service.sh` ist ein dünner Wrapper auf `setup-service.sh`
- Service-Name enthält jetzt den Modus (`transcription-<modus>.service`); alte
  Units werden beim Setup sauber abgelöst
- Statische `transcription-offline.service`-Datei entfernt (Unit wird generiert)

## [1.6.1] - 2026-06-24

### Fixed
- **Layout-korrektes Tippen auf deutscher Tastatur** (`transcription_streaming.py`,
  `transcription_faster_streaming.py`)
  - ydotool sendet rohe US-Keycodes ("we're using raw keycodes now"); auf einem
    deutschen (QWERTZ) Compositor wurden dadurch **Z↔Y vertauscht** und Umlaute/
    Sonderzeichen verstümmelt — das Log war korrekt, nur die getippte Ausgabe nicht
  - Fix: Bei aktivem de-Layout werden jetzt die **richtigen Keycodes für die
    deutsche Belegung** über `ydotool key` gesendet (vollständige T1-Keymap inkl.
    äöüß, @, €). Typografische Zeichen („ " – …) werden auf tippbare gefaltet
  - Layout wird automatisch erkannt (GNOME input-sources → localectl); per
    `STREAM_KBLAYOUT=us|de` überschreibbar
- **Transkription läuft beim Stoppen zu Ende** (`transcription_faster_streaming.py`)
  - Beim Stoppen wurde der letzte ~Sprech-Chunk verschluckt, weil LocalAgreement
    nur über zwei Läufe stabile Wörter festschreibt
  - `OnlineASRProcessor.finish()` macht jetzt einen **finalen Transkriptionslauf**
    über das Rest-Audio und gibt ALLE noch nicht getippten Wörter aus — nichts
    kurz vor dem Stopp Gesprochenes geht mehr verloren

## [1.6.0] - 2026-06-23

### Added
- **Wortweises Echtzeit-Streaming** (`offline/transcription_faster_streaming.py`,
  `run_faster_streaming.sh`)
  - Nutzt **faster-whisper** (CTranslate2) statt openai-whisper — 3-4x schneller,
    weniger RAM, `int8` auf CPU / `float16` auf GPU
  - **LocalAgreement-2** (Macháček et al., "whisper_streaming"): ein wachsender
    Audio-Puffer wird ~jede Sekunde neu transkribiert; nur Wörter, die über ZWEI
    Läufe stabil bleiben, werden festgeschrieben und sofort getippt
  - Dadurch erscheint Text WÄHREND des Sprechens — auch mitten im Satz, nicht
    erst an der Sprechpause wie bei der VAD-Variante (`run_streaming.sh`)
  - Puffer-Beschnitt am letzten bestätigten Wort hält das Modell schnell
  - Neue Tuning-Variablen: `STREAM_MIN_CHUNK` (Update-Takt), `STREAM_MAX_BUFFER`
    (Puffer-Obergrenze), `STREAM_BEAM` (Beam-Size)
  - Gleiche Bedienung (Alt+Alt) und gleiche Tipp-Backends (ydotool/wtype/clipboard)
    wie die übrigen Modi
- `faster-whisper` zu `offline/requirements.txt` und `install.sh` hinzugefügt

## [1.5.0] - 2026-06-23

### Added
- **Echtzeit-Streaming-Transkription** (`offline/transcription_streaming.py`, `run_streaming.sh`)
  - Transkribiert KONTINUIERLICH während des Sprechens statt erst am Ende der Eingabe
  - VAD-basierte Phrasensegmentierung: schneidet an Sprechpausen, nicht mitten im Wort
  - Tippt den erkannten Text live an der Cursor-Position (kein Ctrl+V nötig)
  - Start/Stopp wie gewohnt per Alt+Alt-Doppeltipp
  - Neue Tuning-Variablen: `STREAM_SILENCE_RMS`, `STREAM_MIN_SILENCE`,
    `STREAM_MIN_PHRASE`, `STREAM_MAX_PHRASE`
- **Live-Tippen am Cursor** mit automatischer Backend-Erkennung:
  - `ydotool` (Kernel-uinput) — funktioniert auf GNOME/Mutter (Wayland)
  - `wtype` (virtual-keyboard) — für wlroots-Compositors (Sway/Hyprland)
  - Zwischenablage (`wl-copy`) als Fallback
  - `ydotoold` wird bei Bedarf automatisch im User-Kontext gestartet
- `install.sh` installiert jetzt zusätzlich `ydotool` und `wtype`

### Fixed
- `install.sh` referenzierte gelöschte `online/`-Dateien (Installation brach mit
  `set -e` ab) — entfernt

## [1.4.0] - 2026-05-22

### Added
- Wayland-Unterstützung für Clipboard via `wl-copy` (wl-clipboard)
  - Alle Skripte (offline, online, text_improvement) nutzen jetzt `wl-copy`
  - Systemd-Service: `DISPLAY`/`XAUTHORITY` durch `WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` ersetzt

### Changed
- Geräteauswahl-Menü: Enter ohne Eingabe wählt jetzt Default-Gerät
  - Prompt zeigt `Enter=Default` als Hinweis
- Beep-Sound: `paplay` statt `sounddevice` (kein ALSA/PipeWire-Konflikt mehr)
- Auto-Restart: `run_offline.sh` startet bei Absturz automatisch neu

### Removed
- Alle X11-Abhängigkeiten entfernt: `xclip`, `xsel`, `xdotool`
  - `install.sh` und `offline/install.sh` installieren jetzt `wl-clipboard` statt X11-Tools

## [1.3.0] - 2026-05-16

### Added
- Neuer Modus `-a`/`--auto`: Ein Gerät für Input + Output auswählen
  - Praktisch für Headsets mit Mikrofon (z.B. Jabra SPEAK 510)
  - Zeigt nur Geräte mit Input + Output Kanälen
- Verbesserter `--help` Output mit vollständiger Dokumentation
  - Tastenkürzel (Alt+Alt, Ctrl+C)
  - Alle Umgebungsvariablen erklärt
  - Konkrete Beispiele mit Kommandos
- Täglicher Trivy Security Scan (cron, 2:00 Uhr)
  - Scannt `/home/aroc/projects` auf Vulnerabilities
  - Reports in `~/.transcription/trivy-reports/`
  - Automatische Bereinigung nach 7 Tagen

### Changed
- Start-Verhalten umgekehrt:
  - `./run_offline.sh` → Interaktive Geräteauswahl (war: kein Menü)
  - `./run_offline.sh -d` → Schnellstart mit Defaults (ersetzt altes Default-Verhalten)
  - `./run_offline.sh -a` → Ein Gerät für Input + Output
- Argumente werden jetzt korrekt durch Wrapper-Scripts weitergegeben (`"$@"`)

### Fixed
- `-H` Flag funktioniert jetzt in `run_offline.sh` und `offline/run.sh`
- Argumente wurden nicht an Python-Script weitergegeben (fehlende `"$@"`)

## [1.2.1] - 2026-05-12

### Fixed
- User-Service: Clipboard-Zugriff repariert
  - `DISPLAY=:0` und `XAUTHORITY` hinzugefügt, damit xclip funktioniert
  - Vorher: Transkription funktionierte, aber Text ging nicht in Zwischenablage
  - Jetzt: Service und run_offline.sh arbeiten identisch

## [1.2.0] - 2026-05-09

### Added
- User-Service statt System-Service: `~/.config/systemd/user/transcription-offline.service`
  - Läuft als normaler User → PipeWire/Audio funktioniert nativ
  - Kein `DISPLAY`/`XAUTHORITY`-Workaround mehr nötig
  - Verwalten ohne sudo: `systemctl --user start/stop/status transcription-offline.service`
- `run_offline.sh` im Projektroot für bequemen Start ohne Verzeichniswechsel
- Interaktive Geräte-Auswahl mit `-H` Flag
  - `./run.sh` → nutzt Default-Devices automatisch (schnell)
  - `./run.sh -H` → zeigt Geräte-Auswahl-Menü
  - Umgebungsvariablen (`AUDIO_DEVICE`, `AUDIO_OUTPUT_DEVICE`) haben immer Vorrang

### Changed
- `run.sh` und `run_offline.sh` starten jetzt ohne `sudo`
- Voraussetzung: User muss in der Gruppe `input` sein (einmalige Einrichtung)

### Setup (einmalig)
```bash
sudo usermod -aG input $USER
# Ausloggen und wieder einloggen, damit Gruppe aktiv wird
systemctl --user daemon-reload
systemctl --user enable --now transcription-offline.service
```

### System-Service vs. User-Service

| | System-Service | User-Service |
|---|---|---|
| Läuft als | root | $USER |
| Startet | beim Booten | beim Login |
| Audio | braucht Env-Variablen-Hacks | funktioniert direkt |
| Verwalten | `sudo systemctl` | `systemctl --user` |

## [1.1.0] - 2026-04-30

### Added
- 🔊 Audio-Feedback-Sounds für Aufnahmestart und -stopp
  - 800Hz Beep beim Aufnahmestart
  - 1200Hz Beep wenn Aufnahme endet und Text in Zwischenablage kopiert ist
- Flexible Paketversionen in requirements.txt für bessere Kompatibilität

### Fixed
- 🐛 Installation: PEP 668 Kompatibilität (--break-system-packages Flag hinzugefügt)
- 🐛 Hardcodierter Pfad `/home/aroc/PycharmProjects` entfernt
- 🐛 run.sh nutzt jetzt korrekte venv-Pfade mit sudo -E
- 🐛 offline/install.sh versucht nicht mehr, non-existent `transcription_online.py` zu löschen
- 🐛 Ungültige Paketversion `whisper==20240930` in `openai-whisper>=1.0` geändert

## [1.0.0] - 2026-04-28

### Added
- ✅ Master Installer - globale Installation funktioniert jetzt
- ✅ Offline Transkription mit OpenAI Whisper
- ✅ Online Transkription mit Google Speech API
- ✅ Tastatur-Hotkeys (Alt Tap Tap zum Start/Stop)
- ✅ Audio-Aufnahme mit sounddevice
- ✅ Text-zu-Zwischenablage Kopieren (xclip/xsel)
- ✅ Logging in Datei und Konsole
- ✅ CUDA GPU-Unterstützung für Whisper
- ✅ Separate Tools in verschiedenen Verzeichnissen

### Features
- **Offline-Modus**: Funktioniert ohne Internet, verwendet lokales Whisper-Modell
- **Online-Modus**: Nutzt Google Cloud Speech API für höhere Genauigkeit
- **Multi-Gerät**: Auswahl aus verfügbaren Mikrofonen beim Start
- **Automatische Zwischenablage**: Transkribierter Text wird sofort in Zwischenablage kopiert
- **Detailliertes Logging**: Alle Aktionen werden protokolliert

### Technical
- Python 3.12+
- PyTorch 2.x mit CUDA 13 Unterstützung
- sounddevice/soundfile für Audio
- evdev für Tastaturüberwachung
- OpenAI Whisper für Spracherkennung
