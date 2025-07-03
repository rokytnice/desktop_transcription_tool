Schreibe mir ein Programm in Python, das audio Ausgaben auf meinem Speaker transkrippiert.
 Nach einer erkennbaren Pause, die konfigurierbar ist, soll die Audio in Text umgewandelt werden.
 Der Text soll dann  an einem LLM geschickt werden verwende  "gemini-2.5-flash-lite-preview-06-17"
 die env var GEMINI_API_KEY hat den api key  
 GOOGLE_LLM enthält den llm name "gemini-2.5-flash-lite-preview-06-17" und überschreibt den verwendete wert
(GOOGLE_LLM=gemini-2.5-flash-lite-preview-06-17)

Audioausgabe deines Systems überwachen, sie mit Whisper transkribieren und den Text zur Analyse an das von dir angegebene Gemini-Modell senden.

der transkripierte text soll an 
 - openai wisper lib
  
 Selbstverständlich. Ich habe den Code so angepasst, dass der Name des Gemini-Modells flexibel über die Umgebungsvariable GOOGLE_LLM gesteuert werden kann.Das hat den Vorteil, dass du das Modell wechseln kannst (z.B. von gemini-1.5-flash-latest zu gemini-1.5-pro-latest), ohne den Python-Code selbst ändern zu müssen.



Skript erweitert, sodass es jetzt sowohl den System-Sound (Lautsprecher) als auch das Standard-Mikrofon als Audioquelle nutzen kann. Wie gewünscht, kann die Pausendauer für das Mikrofon separat konfiguriert werden.
beides sol zusammen gehen
 
 
