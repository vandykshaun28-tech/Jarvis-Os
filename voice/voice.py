import threading
import queue
import subprocess
import base64

CREATE_NO_WINDOW = 0x08000000


class JarvisVoice:
    """
    Same public interface as before (speak(text)), but instead of spawning
    a fresh PowerShell process + reloading System.Speech on every call
    (which is what caused the ~10s startup delay), this keeps ONE
    PowerShell process alive for the life of the app and just sends it
    text over stdin. Speak commands execute near-instantly once the
    process is warm.

    Text is base64-encoded before being sent to PowerShell, so there is
    no quote-escaping to get wrong — arbitrary text (quotes, apostrophes,
    unicode) is safe to speak as-is.
    """

    def __init__(self):
        self.queue = queue.Queue()
        self._proc = None
        self._start_engine()
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()
        print("[Voice] SAPI voice engine ready (persistent process).")

    # ── engine lifecycle ─────────────────────────────────────────────
    def _start_engine(self):
        """Launch one long-lived PowerShell process with the speech
        synthesizer already constructed, waiting on stdin for base64
        text to speak — one line per utterance."""
        bootstrap = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Rate = 1;"
            "$s.Volume = 100;"
            "$s.SelectVoiceByHints('Male');"
            "while ($line = [Console]::In.ReadLine()) {"
            "  if ($line -eq '__EXIT__') { break };"
            "  try {"
            "    $bytes = [System.Convert]::FromBase64String($line);"
            "    $text = [System.Text.Encoding]::UTF8.GetString($bytes);"
            "    $s.Speak($text);"
            "  } catch {}"
            "}"
        )
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", bootstrap],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            bufsize=1,  # line-buffered
        )

    def _restart_engine_if_dead(self):
        if self._proc is None or self._proc.poll() is not None:
            print("[Voice] Engine process died — restarting.")
            self._start_engine()

    # ── public API (unchanged) ───────────────────────────────────────
    def speak(self, text: str):
        self.queue.put(text)

    # ── worker loop ───────────────────────────────────────────────────
    def _loop(self):
        while True:
            text = self.queue.get()
            try:
                self._say(text)
            except Exception as e:
                print(f"[Voice] Error: {e}")
            self.queue.task_done()

    def _say(self, text: str):
        if not text or not text.strip():
            return
        self._restart_engine_if_dead()
        try:
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            self._proc.stdin.write(encoded + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            print(f"[Voice] Pipe broken ({e}), restarting engine and retrying once.")
            self._start_engine()
            try:
                encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
                self._proc.stdin.write(encoded + "\n")
                self._proc.stdin.flush()
            except Exception as e2:
                print(f"[Voice] Retry failed: {e2}")

    def shutdown(self):
        """Optional: call on app close to cleanly stop the engine process."""
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.stdin.write("__EXIT__\n")
                self._proc.stdin.flush()
                self._proc.terminate()
        except Exception:
            pass