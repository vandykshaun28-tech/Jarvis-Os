import threading
import queue
import subprocess


CREATE_NO_WINDOW = 0x08000000


class JarvisVoice:

    def __init__(self):
        self.queue = queue.Queue()
        self.worker = threading.Thread(
            target=self._loop,
            daemon=True
        )
        self.worker.start()
        print("[Voice] SAPI voice engine ready.")

    def speak(self, text: str):
        self.queue.put(text)

    def _loop(self):
        while True:
            text = self.queue.get()
            try:
                self._say(text)
            except Exception as e:
                print(f"[Voice] Error: {e}")
            self.queue.task_done()

    def _say(self, text: str):
        safe = text.replace("'", "''").replace('"', '')
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Rate = 1;"
            "$s.Volume = 100;"
            f"$s.SelectVoiceByHints('Male');"
            f"$s.Speak('{safe}');"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            timeout=30,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW
        )