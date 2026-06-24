# Service & Autostart

_Zuletzt aktualisiert: 2026-06-24_

## Überblick

Der Transcription-Tool läuft als **systemd-User-Service** (`transcription.service`)
und startet automatisch bei Rechnerstart. Eingerichtet wird er mit
`./setup-service.sh [MODUS]` (Wrapper: `enable-service.sh`).

## Warum User-Service (nicht System-Service)

Das Tool tippt Text an der **Cursor-Position der aktiven Wayland-Sitzung** und
braucht dafür `WAYLAND_DISPLAY` + `XDG_RUNTIME_DIR` des eingeloggten Users. Ein
System-Service (root, vor Login) hätte keine Sitzung zum Hineintippen. Deshalb:
User-Service.

## Wie der Autostart bei Rechnerstart funktioniert

Zwei Bausteine zusammen:

1. **`loginctl enable-linger $USER`** — der systemd-User-Manager wird schon beim
   **Boot** hochgefahren (nicht erst beim ersten Login). Ohne Linger liefe der
   User-Manager nur während einer aktiven Login-Session.
2. **`WantedBy=graphical-session.target`** + `After/Wants/PartOf=graphical-session.target`
   — die Unit startet erst, wenn die **grafische (Wayland-)Sitzung** bereit ist,
   und stoppt mit ihr. So tippt der Service nie ins Leere, bevor eine Sitzung da
   ist.

`Restart=always` + `RestartSec=10` fangen transiente Fehler ab (z. B. PipeWire
noch nicht ganz oben).

## setup-service.sh — was es macht

- Modus wählbar: `faster-streaming` (Standard), `streaming`, `offline`
  → mappt auf `offline/transcription_*.py -a` (`-a` = ein Audio-Gerät für In+Out,
  kein interaktives Menü — service-tauglich)
- Erkennt **alle Pfade automatisch** (Repo, `offline/.venv`, `XDG_RUNTIME_DIR`,
  `WAYLAND_DISPLAY`) — nichts hartkodiert, funktioniert auch nach Repo-Umzug
- Optionen: `--model NAME`, `--device IDX`, `--no-start`
- Generiert `~/.config/systemd/user/transcription.service` **dynamisch**
  (kein statisches Unit-File mehr im Repo)
- Installiert globale Kommandos `transcription-{start,stop,restart,status,log}`
- Löst eine evtl. vorhandene alte `transcription-offline.service` sauber ab
  (disable + entfernen), damit nie zwei Services gleichzeitig tippen

`install.sh` delegiert die Service-Einrichtung an `setup-service.sh`
(`--no-start`); Modus per `TRANSCRIPTION_MODE=…` überschreibbar.

## Steuerung

| Kommando | Funktion |
|---|---|
| `transcription-status`  | Status |
| `transcription-restart` | Neu starten |
| `transcription-start` / `transcription-stop` | Start / Stop |
| `transcription-log`     | Live-Log (`journalctl --user -u transcription.service -f`) |

## Gotchas

- **App-Log nicht im Journal:** Die Python-App schreibt ihr eigenes Logfile im
  `offline/`-Verzeichnis; im `journalctl` steht nur die systemd-Startzeile. Für
  App-Diagnose das Logfile ansehen, nicht nur das Journal.
- **Modus wechseln:** Einfach `./setup-service.sh <anderer-modus>` erneut
  ausführen — die Unit wird überschrieben und neu gestartet.
- **Linger lässt sich prüfen:** `loginctl show-user $USER -p Linger`.
