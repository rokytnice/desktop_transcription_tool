# Real-Time Streaming Transcription 🎤⚡

Sprache wird **direkt während des Sprechens** transkribiert und in das aktive Fenster eingegeben.

## Wie es funktioniert

1. **Alt + Alt** (zweimal schnell drücken) → Streaming startet
2. **Sprechen** → Text erscheint in Echtzeit im aktuellen Fenster
3. **Alt + Alt** (zweimal) → Streaming stoppt

Der Text wird Wort für Wort oder Satz für Satz eingegeben, während Whisper die Audio verarbeitet.

## Start

```bash
./run_streaming.sh                # Default-Geräte
./run_streaming.sh -H             # Geräte-Auswahl-Menü
```

## Unterschied zu `run.sh`

| Feature | run.sh (Stop & Go) | run_streaming.sh (Echtzeit) |
|---|---|---|
| Bedienung | Alt+Alt → record → Alt+Alt → transkribiert | Alt+Alt → sofort transkribieren → Alt+Alt stop |
| Output | Alles auf einmal nach Transkription | Wort für Wort während des Sprechens |
| Latenz | ~3-5 Sekunden | ~2 Sekunden pro Chunk |
| Nutzung | Text-Blöcke | Live-Typing |

## Performance

- **Chunk-Größe**: 2 Sekunden Audio
- **Modell**: small (standard)
- **Sprache**: Deutsch (fest codiert)
- **CPU**: ~5-10% bei normaler Rede

## Logs

```bash
tail -f ~/.transcription/transcription_streaming.log
```

## Troubleshooting

**Text wird nicht eingegeben?**
- Stelle sicher, dass das Fenster aktiv ist (Focus)
- xdotool muss installiert sein: `sudo apt install xdotool`

**Transkription ist falsch?**
- Sprich deutlicher
- Nutze ein besseres Mikrofon
- Wechsle Modell in Umgebungsvariable: `WHISPER_MODEL=base` oder `medium`
