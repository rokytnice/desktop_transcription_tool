# Tool Description

To start the voice input recording, press and hold the Control and Alt keys simultaneously.
To stop the recording, simply release both keys.

The transcribed text will then automatically appear at the cursor's position in the active window.



# Developer Setup
Developer Setup


You need python 3 and google API Key to use google transcription web service.


 ```
 pip install 
 python3 transcription_listener.py 
 pip install --upgrade pip
 python3 -m venv .venv
 source myenv/bin/activate
 pip install -r requirements.txt
 pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

export API_KEY=***

```


 python3 transcription_listener.py 
