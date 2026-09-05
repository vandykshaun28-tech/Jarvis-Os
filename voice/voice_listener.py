"""
voice_listener.py
─────────────────
JARVIS voice input using sounddevice + SpeechRecognition.
No PyAudio required.

Changes from the previous version:
  - Silent audio is no longer sent to the Google API at all (RMS check
    before transcribing), so it stops burning API calls/quota on dead
    air and stops the intermittent "doesn't hear me" rate-limit issue.
  - Command capture after the wake word is now silence-terminated
    instead of a hard fixed 5-second window: it starts collecting once
    you start talking and stops shortly after you stop, so it neither
    cuts you off mid-sentence nor sits there waiting once you're done.
  - mute()/unmute() added so the HUD can silence the listener while
    Jarvis's TTS is playing, preventing Jarvis from hearing himself.
"""

import os
import sys
import threading
import time
import io
import wave
import numpy as np
import sounddevice as sd
import speech_recognition as sr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config as _config
    _MIC_INDEX = getattr(_config, "MIC_DEVICE_INDEX", None)
    _MIC_NAME  = (getattr(_config, "MIC_DEVICE_NAME", "") or "").strip()
except Exception:
    _MIC_INDEX = None
    _MIC_NAME  = ""


def _find_device_by_name(fragment: str):
    """First input device whose name contains the fragment (case-insensitive).
    Names survive reboots and Bluetooth reshuffles; indices don't."""
    frag = fragment.lower()
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0 and frag in d.get("name", "").lower():
            return i, d.get("name", "?")
    return None, None


def device_report() -> str:
    """Human-readable list of input devices — used by 'voice status'."""
    try:
        lines = []
        default_in = sd.default.device[0]
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                mark = "  ← in use" if i == default_in else ""
                lines.append(f"  [{i}] {d['name']}{mark}")
        return "\n".join(lines) or "  no input devices found"
    except Exception as e:
        return f"  device query failed: {e}"


# ── CONFIG ──────────────────────────────────────
# Her name IS the wake word — no "hey". "Allison" (and common
# mis-hears) wake her. Google STT often returns "allison/alison/
# allie/madison-ish" variants, so we accept the near-misses too.
WAKE_WORDS          = ["allison", "alison", "allisson", "alisson",
                       "hey allison", "ok allison", "alicen", "alyson"]
SAMPLE_RATE         = 16000
CHANNELS            = 1

WAKE_CHUNK_SECONDS  = 3        # window size while listening for the wake word
SILENCE_RMS         = 150      # int16 RMS below this = "silence", skip API call
SPEECH_RMS          = 350      # int16 RMS above this = "someone is talking"

CMD_FRAME_SECONDS   = 0.5      # frame size while recording a command
CMD_MAX_SECONDS     = 12       # hard safety cap on command length
CMD_SILENCE_FRAMES  = 3        # consecutive silent frames (~1.5s) = stop recording
# ────────────────────────────────────────────────


def _rms(raw_bytes: bytes) -> float:
    if not raw_bytes:
        return 0.0
    arr = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr ** 2)))


class VoiceListener:

    def __init__(self, on_command, on_wake=None, on_idle=None):
        self.on_command = on_command
        self.on_wake    = on_wake  or (lambda: None)
        self.on_idle    = on_idle  or (lambda: None)
        self.recognizer = sr.Recognizer()
        self.running    = False
        self.thread     = None
        self._muted     = False
        try:
            if _MIC_NAME:
                idx, name = _find_device_by_name(_MIC_NAME)
                if idx is not None:
                    sd.default.device = (idx, None)
                    print(f"[Voice] Using microphone '{name}' (matched '{_MIC_NAME}').")
                else:
                    print(f"[Voice] No input device matching '{_MIC_NAME}' — "
                          f"using system default.")
            elif _MIC_INDEX is not None:
                sd.default.device = (_MIC_INDEX, None)
                print(f"[Voice] Using microphone device index {_MIC_INDEX}.")
        except Exception as e:
            print(f"[Voice] Could not set mic device: {e}")

    def start(self):
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[Voice] Listener started. Say 'Allison' to activate.")

    def stop(self):
        self.running = False

    def mute(self):
        """Call this right before Jarvis starts speaking, so the mic
        doesn't pick up his own voice as a wake word or command."""
        self._muted = True

    def unmute(self):
        """Call this once Jarvis finishes speaking."""
        self._muted = False

    # ── low-level audio ──────────────────────────
    def _record_seconds(self, seconds) -> bytes:
        audio = sd.rec(
            int(seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16"
        )
        sd.wait()
        return audio.tobytes()

    def _record_frame(self, seconds=CMD_FRAME_SECONDS) -> bytes:
        return self._record_seconds(seconds)

    def _to_wav(self, raw_bytes: bytes) -> io.BytesIO:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw_bytes)
        buf.seek(0)
        return buf

    def _transcribe(self, raw_bytes: bytes) -> str:
        try:
            wav_buf = self._to_wav(raw_bytes)
            with sr.AudioFile(wav_buf) as source:
                audio = self.recognizer.record(source)
            text = self.recognizer.recognize_google(audio)
            return text.lower().strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            print(f"[Voice] Google error: {e}")
            return ""
        except Exception as e:
            print(f"[Voice] Transcribe error: {e}")
            return ""

    def _is_wake_word(self, text: str) -> bool:
        return any(word in text for word in WAKE_WORDS)

    # ── command capture: silence-terminated, not fixed length ───────
    def _record_command(self) -> bytes:
        """
        Records in small frames. Waits for speech to actually start
        (so leading silence doesn't count against the time budget),
        then keeps recording until CMD_SILENCE_FRAMES consecutive
        quiet frames are seen after speech began, or CMD_MAX_SECONDS
        is hit — whichever comes first.
        """
        frames = []
        started = False
        silent_run = 0
        elapsed = 0.0

        while elapsed < CMD_MAX_SECONDS:
            frame = self._record_frame()
            elapsed += CMD_FRAME_SECONDS
            level = _rms(frame)

            if not started:
                if level >= SPEECH_RMS:
                    started = True
                    frames.append(frame)
                # else: still waiting for you to start talking, discard
                continue

            frames.append(frame)
            if level < SILENCE_RMS:
                silent_run += 1
                if silent_run >= CMD_SILENCE_FRAMES:
                    break
            else:
                silent_run = 0

        return b"".join(frames)

    # ── main loop ─────────────────────────────────
    def _loop(self):
        print("[Voice] Calibrating... please wait.")
        time.sleep(1)
        print("[Voice] Listening for wake word...")

        while self.running:
            try:
                if self._muted:
                    time.sleep(0.2)
                    continue

                raw = self._record_seconds(WAKE_CHUNK_SECONDS)

                if self._muted:
                    # Jarvis may have started speaking mid-recording —
                    # discard this chunk rather than risk transcribing
                    # his own voice.
                    continue

                level = _rms(raw)
                if level < SILENCE_RMS:
                    # Pure silence — skip the API call entirely.
                    continue

                text = self._transcribe(raw)
                if not text:
                    continue

                print(f"[Voice] Heard: {text}")

                if self._is_wake_word(text):
                    print("[Voice] Wake word detected!")
                    self.on_wake()

                    print("[Voice] Listening for command...")
                    cmd_raw = self._record_command()
                    command = self._transcribe(cmd_raw)

                    if command:
                        for word in WAKE_WORDS:
                            command = command.replace(word, "").strip()
                        if command:
                            print(f"[Voice] Command: {command}")
                            self.on_command(command)
                        else:
                            print("[Voice] No command after wake word.")
                    else:
                        print("[Voice] No command heard.")

                    self.on_idle()

            except Exception as e:
                print(f"[Voice] Loop error: {e}")
                time.sleep(1)


# ── STANDALONE TEST ─────────────────────────────
if __name__ == "__main__":
    print("Testing JARVIS voice listener...")
    print("Say 'Allison' followed by a command.")
    print("Press Ctrl+C to stop.\n")

    def on_command(text):
        print(f"\n>>> COMMAND: {text}\n")

    def on_wake():
        print(">>> WAKE WORD DETECTED — speak your command now")

    def on_idle():
        print(">>> Back to listening...\n")

    listener = VoiceListener(
        on_command=on_command,
        on_wake=on_wake,
        on_idle=on_idle
    )
    listener.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
        print("\nStopped.")