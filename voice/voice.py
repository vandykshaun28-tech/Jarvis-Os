"""
voice.py
────────
JARVIS's mouth. Two engines:

  1. "neural" (default) — Microsoft Edge neural TTS via the edge-tts
     package. en-GB-RyanNeural is a deep, calm British voice that is
     about as close to the film JARVIS as you can get for free.
     Needs internet; synthesises to an mp3 and plays it through a
     persistent hidden PowerShell MediaPlayer.

  2. "sapi" — the old offline Windows voice. Used automatically as a
     fallback whenever neural synthesis fails (e.g. no internet), so
     JARVIS is never mute.

Both paths report exactly when audio starts and finishes, so the HUD
can mute the microphone while JARVIS speaks (he must not hear himself).
Change the voice in config.py: VOICE_NAME (try en-GB-ThomasNeural,
en-US-GuyNeural) and VOICE_RATE (e.g. "+10%").
"""

import os
import re
import sys
import queue
import base64
import asyncio
import tempfile
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config
    VOICE_ENGINE = getattr(config, "VOICE_ENGINE", "neural")
    VOICE_NAME   = getattr(config, "VOICE_NAME", "en-GB-RyanNeural")
    VOICE_RATE   = getattr(config, "VOICE_RATE", "+4%")
except Exception:
    VOICE_ENGINE, VOICE_NAME, VOICE_RATE = "neural", "en-GB-RyanNeural", "+4%"

try:
    import edge_tts
    EDGE_OK = True
except Exception:
    EDGE_OK = False

CREATE_NO_WINDOW = 0x08000000

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002600-\U000026FF⭐✅❌]+")
_URL = re.compile(r"https?://\S+")


def _speakable(text: str) -> str:
    """Strip things that sound terrible when read aloud."""
    text = _URL.sub("a link", text)
    text = _EMOJI.sub("", text)
    text = text.replace("→", ", then ").replace("•", ",")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class JarvisVoice:

    def __init__(self, on_speaking_start=None, on_speaking_end=None):
        self.on_speaking_start = on_speaking_start
        self.on_speaking_end   = on_speaking_end
        self.muted   = False
        self.queue   = queue.Queue()
        self._sapi   = None      # persistent SAPI PowerShell (fallback)
        self._player = None      # persistent MediaPlayer PowerShell (neural)
        self.engine  = "neural" if (EDGE_OK and VOICE_ENGINE == "neural") else "sapi"
        if self.engine == "sapi":
            self._start_sapi()
        else:
            self._start_player()
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()
        print(f"[Voice] Engine ready: {self.engine} "
              f"({VOICE_NAME if self.engine == 'neural' else 'Windows SAPI'})")

    # ── public API ───────────────────────────────
    def speak(self, text: str):
        if not self.muted:
            self.queue.put(text)

    def stop_now(self):
        """Cut him off mid-sentence and drop anything queued."""
        try:
            while True:
                self.queue.get_nowait()
                self.queue.task_done()
        except queue.Empty:
            pass
        # terminate the active playback process — the worker's wait for
        # __DONE__ unblocks immediately; engines restart lazily on the
        # next utterance
        for proc in (self._player, self._sapi):
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass

    def set_muted(self, muted: bool):
        self.muted = bool(muted)
        if self.muted:
            self.stop_now()

    def shutdown(self):
        for proc in (self._sapi, self._player):
            try:
                if proc and proc.poll() is None:
                    proc.stdin.write("__EXIT__\n")
                    proc.stdin.flush()
                    proc.terminate()
            except Exception:
                pass

    # ── worker ───────────────────────────────────
    def _loop(self):
        while True:
            text = self.queue.get()
            try:
                if not self.muted:
                    self._say(text)
            except Exception as e:
                print(f"[Voice] Error: {e}")
            self.queue.task_done()

    def _say(self, text: str):
        text = _speakable(text)
        if not text:
            return
        if self.on_speaking_start:
            try: self.on_speaking_start()
            except Exception: pass
        try:
            ok = False
            if self.engine == "neural":
                ok = self._say_neural(text)
            if not ok:
                self._say_sapi(text)
        finally:
            if self.on_speaking_end:
                try: self.on_speaking_end()
                except Exception: pass

    # ── neural engine (edge-tts + MediaPlayer) ───
    def _start_player(self):
        bootstrap = (
            "Add-Type -AssemblyName PresentationCore;"
            "$p = New-Object System.Windows.Media.MediaPlayer;"
            "while ($line = [Console]::In.ReadLine()) {"
            "  if ($line -eq '__EXIT__') { break };"
            "  try {"
            "    $p.Open([Uri]$line); $p.Play();"
            "    $w = 0;"
            "    while (-not $p.NaturalDuration.HasTimeSpan -and $w -lt 50)"
            "      { Start-Sleep -m 100; $w++ };"
            "    if ($p.NaturalDuration.HasTimeSpan) {"
            "      $d = $p.NaturalDuration.TimeSpan.TotalMilliseconds;"
            "      $t = 0;"
            "      while ($p.Position.TotalMilliseconds -lt $d -and $t -lt $d + 3000)"
            "        { Start-Sleep -m 150; $t += 150 };"
            "    };"
            "    $p.Close();"
            "  } catch {};"
            "  [Console]::Out.WriteLine('__DONE__');"
            "}"
        )
        self._player = subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", bootstrap],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
            text=True, bufsize=1)

    def _say_neural(self, text: str) -> bool:
        try:
            path = os.path.join(tempfile.gettempdir(), "jarvis_tts.mp3")
            asyncio.run(edge_tts.Communicate(
                text, VOICE_NAME, rate=VOICE_RATE).save(path))
            if self._player is None or self._player.poll() is not None:
                self._start_player()
            self._player.stdin.write(path + "\n")
            self._player.stdin.flush()
            while True:
                line = self._player.stdout.readline()
                if not line or line.strip() == "__DONE__":
                    break
            return True
        except Exception as e:
            print(f"[Voice] Neural TTS failed ({e}) — falling back to SAPI.")
            return False

    # ── SAPI fallback (offline) ──────────────────
    def _start_sapi(self):
        bootstrap = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Rate = 1; $s.Volume = 100;"
            "$s.SelectVoiceByHints('Male');"
            "while ($line = [Console]::In.ReadLine()) {"
            "  if ($line -eq '__EXIT__') { break };"
            "  try {"
            "    $bytes = [System.Convert]::FromBase64String($line);"
            "    $text = [System.Text.Encoding]::UTF8.GetString($bytes);"
            "    $s.Speak($text);"
            "  } catch {};"
            "  [Console]::Out.WriteLine('__DONE__');"
            "}"
        )
        self._sapi = subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", bootstrap],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
            text=True, bufsize=1)

    def _say_sapi(self, text: str):
        if self._sapi is None or self._sapi.poll() is not None:
            self._start_sapi()
        try:
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            self._sapi.stdin.write(encoded + "\n")
            self._sapi.stdin.flush()
            while True:
                line = self._sapi.stdout.readline()
                if not line or line.strip() == "__DONE__":
                    break
        except (BrokenPipeError, OSError) as e:
            print(f"[Voice] SAPI pipe broken ({e}).")
