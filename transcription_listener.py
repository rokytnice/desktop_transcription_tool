import os
import json
import logging
import requests
import difflib
import time
from pathlib import Path
from typing import List, Dict
from threading import Thread

# Konfiguration für Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

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

    def show_progress(self):
        self.stop_progress = False
        symbols = [".", "..", "..."]
        idx = 0
        while not self.stop_progress:
            print(f"Waiting for API response{symbols[idx % len(symbols)]}", end="\r")
            idx += 1
            time.sleep(0.5)

class FileManager:
    def __init__(self, base_directory: Path):
        self.base_directory = base_directory

    def find_files(self, patterns: List[str]) -> List[Path]:
        files = []
        for pattern in patterns:
            files.extend(self.base_directory.rglob(pattern))
        logging.info(f"Files matching patterns {patterns}: {files}")
        return files

    def read_file_content(self, file_path: Path) -> str:
        logging.info(f"Reading content from file: {file_path}")
        return file_path.read_text(encoding='utf-8')

    def write_file_content(self, file_path: Path, content: str):
        if not file_path.parent.exists():
            logging.info(f"Creating directories for path: {file_path.parent}")
            file_path.parent.mkdir(parents=True, exist_ok=True)
        old_content = file_path.read_text(encoding='utf-8') if file_path.exists() else ""
        file_path.write_text(content, encoding='utf-8')
        logging.info(f"File written: {file_path}")
        self.log_diff(file_path, old_content, content)

    def log_diff(self, file_path: Path, old_content: str, new_content: str):
        if old_content != new_content:
            logging.info(f"Changes in file {file_path}:")
            diff = difflib.unified_diff(
                old_content.splitlines(),
                new_content.splitlines(),
                fromfile="Old Content",
                tofile="New Content",
                lineterm=""
            )
            for line in diff:
                logging.info(line)

class PromptProcessor:
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    def build_prompt(self, base_prompt: str, paths: List[Path], patterns: List[str] = ["*"]) -> str:
        prompt = base_prompt
        for path in paths:
            if path.is_dir():
                files = self.file_manager.find_files(patterns)
                for file in files:
                    content = self.file_manager.read_file_content(file)
                    prompt += f"\n\n---\n{file}:{content}"  # Dateiinhalt hinzufügen
            elif path.is_file():
                content = self.file_manager.read_file_content(path)
                prompt += f"\n\n---\n{path}:{content}"
        logging.info(f"Constructed prompt: {prompt}")
        return prompt

class ResponseHandler:
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager

    def process_response(self, response: Dict):
        candidates = response.get("candidates", [])
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                if "```java" in part["text"]:
                    java_content = self.extract_code(part["text"], "java")
                    if java_content:
                        self.update_files(java_content)

    def extract_code(self, text: str, language: str) -> str:
        start_tag = f"```{language}"
        end_tag = "```"
        start = text.find(start_tag) + len(start_tag)
        end = text.find(end_tag, start)
        return text[start:end].strip() if start_tag in text and end > start else ""

    def update_files(self, content: str):
        # Extract file name and content
        lines = content.splitlines()
        if lines:
            file_name = lines[0].strip()
            file_content = "\n".join(lines[1:])
            file_path = self.file_manager.base_directory / file_name
            self.file_manager.write_file_content(file_path, file_content)

# Hauptprogramm
if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("API key is missing. Set GEMINI_API_KEY as an environment variable.")

    base_directory = Path("/home/andre/IdeaProjects/algosec-connector")
    file_manager = FileManager(base_directory)
    prompt_processor = PromptProcessor(file_manager)
    api_client = APIClient(api_key)
    response_handler = ResponseHandler(file_manager)

    # Beispiel-Aufruf
    paths = [base_directory]
    base_prompt = "Aktualisiere CustomAuthenticationFailureHandler.java Java-Klasse Füge eine error code hinzu."
    patterns = ["*.java", "*.md"]  # Beispiel für Glob-Muster

    constructed_prompt = prompt_processor.build_prompt(base_prompt, paths, patterns)
    try:
        response = api_client.send_prompt(constructed_prompt)
        response_handler.process_response(response)
    except Exception as e:
        logging.error(f"Error occurred: {e}")
