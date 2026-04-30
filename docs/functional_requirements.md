Fachliche Anforderungen an das Skript
1. Verarbeitung von API-Anfragen
Das System muss in der Lage sein, Textinhalte (Prompts) an eine externe generative Sprach-API zu senden.
Während des API-Aufrufs soll eine visuelle Fortschrittsanzeige auf der Konsole den aktuellen Status signalisieren.
Nach Abschluss des API-Aufrufs sollen die erhaltenen Antworten analysiert und relevante Inhalte extrahiert werden.
2. Integration mit dem Dateisystem
Das System muss Dateien anhand von definierten Mustern (z. B. *.java, *.md) in einem festgelegten Verzeichnis finden können.
Es soll möglich sein, Inhalte von Dateien auszulesen und zur Verarbeitung weiterzuverwenden.
Änderungen an Dateien müssen vorgenommen und gespeichert werden, wobei Verzeichnisse bei Bedarf automatisch erstellt werden.
3. Protokollierung und Nachvollziehbarkeit
Alle Aktionen, einschließlich API-Aufrufe, Dateiänderungen und Fehler, müssen zentral geloggt werden.
Änderungen an Dateien sollen durch einen Vergleich zwischen altem und neuem Inhalt (Unified-Diff) protokolliert werden, um die Nachvollziehbarkeit sicherzustellen.
4. Dynamische Erstellung von API-Prompts
Das System muss Textprompts dynamisch erstellen, indem Basisanfragen mit Datei- oder Verzeichnisinhalten kombiniert werden.
Es muss möglich sein, verschiedene Dateimuster und Verzeichnisse für die Erstellung der Prompts anzugeben.
5. Verarbeitung von API-Antworten
Antworten der API, die Codefragmente enthalten, müssen erkannt und korrekt extrahiert werden.
Extrahierter Code soll in eine spezifische Datei geschrieben werden, wobei Dateipfade und -namen aus dem Inhalt der API-Antwort abgeleitet werden.
6. Fehlerbehandlung
Wenn der API-Schlüssel fehlt, muss das System eine entsprechende Fehlermeldung ausgeben und den Prozess abbrechen.
Fehler während der Datei- oder API-Verarbeitung müssen abgefangen und geloggt werden, ohne den gesamten Prozess zu unterbrechen.
7. Benutzerfreundlichkeit
Fortschrittsanzeigen während der Verarbeitung sollen den Nutzer über laufende Prozesse informieren.
Das System soll flexibel und erweiterbar sein, indem es unterschiedliche Dateitypen und -muster unterstützt.
Zusätzliche Rahmenbedingungen
Alle Verzeichnisse und Pfade müssen flexibel konfigurierbar sein.
Der Betrieb des Systems setzt einen gültigen API-Schlüssel voraus, der über Umgebungsvariablen bereitgestellt wird.


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class APIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def send_prompt(self, prompt: str) -> Dict:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        logging.info(f"Sending API request with payload: {json.dumps(payload)}")

        # Start progress indicator in a separate thread
        progress_thread = Thread(target=self.show_progress, daemon=True)
        progress_thread.start()

        try:
            response = requests.post(f"{API_URL}?key={self.api_key}", headers=headers, json=payload)
            response.raise_for_status()
            logging.info(f"Received API response: {response.text}")
            return response.json()
        finally:
            # Stop the progress indicator
            self.stop_progress = True
            progress_thread.join()

   