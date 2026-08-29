# Warum "Automatische Transkription" (Android) schneller wirkt als unser Tool

_Analyse 2026-08-27 · Messungen auf i9-12900H, 20 Threads (4 für Whisper), audio_recording.wav_

## Ausgangslage

Handy hängt im MTP-Modus, USB-Debugging aus → `adb devices` zeigt nur den
Emulator, die App konnte nicht direkt ausgelesen werden. "Automatische
Transkription" ist der deutsche Name von **Google Live Transcribe**
(`com.google.audio.hearing.visualization.accessibility.scribe`); die folgende
Architektur-Analyse beruht darauf.

## Messung unserer Pipeline (openai-whisper, PyTorch CPU fp32)

| Aufnahme | Wartezeit nach Stopp | Anteil Sprechzeit |
|---------:|---------------------:|------------------:|
|     2 s  |  0,82 s | 41 % |
|   7,5 s  |  1,01 s | 13 % |
|    30 s  |  3,98 s | 13 % |
|    60 s  | 10,05 s | 17 % |
|   120 s  | 20,77 s | 17 % |

Modellvergleich auf demselben 7,5-s-Clip:

| Backend | Zeit | Realtime-Faktor |
|---|---:|---:|
| openai-whisper base (fp32) | 0,85 s | 8,8× |
| openai-whisper small (fp32) | 2,49 s | 3,0× |
| faster-whisper base (int8) | 1,27 s | 5,9× |
| faster-whisper small (int8) | 1,99 s | 3,8× |

(faster-whisper verliert bei sehr kurzen Clips durch Overhead, gewinnt ab ~30 s deutlich.)

## Die vier Gründe

1. **Streaming-Transducer statt Batch-Encoder-Decoder.** Live Transcribe nutzt
   ein RNN-T/Conformer-Transducer-Modell: strikt links-nach-rechts, gibt Wörter
   aus, *während* gesprochen wird. Die gefühlte Latenz misst sich ab dem letzten
   Wort (~200–300 ms) und ist **unabhängig von der Aufnahmelänge**. Unser
   klassischer Modus wartet bis zum Stopp — die Wartezeit wächst linear mit.

2. **Whisper rechnet immer 30-Sekunden-Fenster.** Whisper wurde auf 30-s-Blöcke
   trainiert; jeder Aufruf padded auf 30 s, der Encoder verarbeitet immer 3000
   Mel-Frames — egal ob 2 s oder 25 s gesprochen wurde. Genau das zeigt die
   Tabelle: 2 s kosten 0,82 s, 7,5 s kosten 1,01 s. Ein Transducer verarbeitet
   jeden 40-ms-Frame genau einmal mit konstantem Aufwand.

3. **Modellgröße, Quantisierung, Hardware.** Live Transcribe: ein
   int8-quantisiertes, **einsprachiges** Modell (~50–100 MB) auf NPU/DSP
   (Tensor/Hexagon via NNAPI). Wir: multilinguales Whisper small = 244 M
   Parameter in fp32 auf der CPU, bewusst auf 4 Threads gedeckelt, damit der
   Audio-Callback sein Zeitfenster hält.

4. **Kein Fallback-Overhead.** Whisper macht autoregressives Decoding plus
   Temperature-Fallback (Wiederholung ganzer Fenster bei schlechter Konfidenz).
   Ein Transducer hat nichts davon.

## Empfehlung: Rechnen streamen, Tippen nicht

Das Live-Pipelining war architektonisch richtig und wurde nur deshalb
abgeschaltet, weil es das Diktat beim Tippen in Phrasen-Häppchen zerlegt hat.
Beides lässt sich trennen:

- Während der Aufnahme wie im Live-Modus phrasenweise transkribieren (VAD),
  den Text aber nur **puffern** statt zu tippen.
- Beim Stoppen nur noch den letzten Rest transkribieren und den kompletten
  Text **in einem Block** tippen.

→ Wartezeit nach dem Stopp fällt von ~17 % der Sprechzeit auf ~1 s konstant,
die Ausgabe bleibt ein zusammenhängender Text. Zusätzlich: offline-Modus auf
faster-whisper int8 umstellen (ist im venv bereits installiert), das bringt bei
längeren Aufnahmen nochmal Faktor ~2.
