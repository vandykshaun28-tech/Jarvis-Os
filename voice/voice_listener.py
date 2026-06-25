"""
voice_listener.py
─────────────────
JARVIS voice input using sounddevice + SpeechRecognition.
No PyAudio required.
"""

import threading
import queue
import io
import wave
import time
import numpy as np
import sounddevice as sd
import speech_recognition as sr


# ── CONFIG ──────────────────────────────────────
WAKE_WORDS        = ["hey jarvis", "ok jarvis"]
SAMPLE_RATE       = 16000
CHANNELS          = 1
RECORD_SECONDS    = 3
SILENCE_THRESHOLD = 0.01 # volume threshold for silence detection # type: ignore
# ────────────────────────────────────────────────


class VoiceListener:

    def __init__(self, on_command, on_wake=None, on_idle=None):
        self.on_command = on_command
        self.on_wake    = on_wake  or (lambda: None)
        self.on_idle    = on_idle  or (lambda: None)
        self.recognizer = sr.Recognizer()
        self.running    = False
        self.thread     = None

    def start(self):
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[Voice] Listener started. Say 'Hey JARVIS' to activate.")

    def stop(self):
        self.running = False

    def _record(self, seconds=3):
        """Record audio using sounddevice and return as bytes."""
        print(f"[Voice] Recording {seconds}s...")
        audio = sd.rec(
            int(seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16"
        )
        sd.wait()
        return audio.tobytes()

    def _to_wav(self, raw_bytes):
        """Convert raw PCM bytes to WAV bytes for SpeechRecognition."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw_bytes)
        buf.seek(0)
        return buf

    def _transcribe(self, raw_bytes) -> str:
        """Convert raw audio bytes to text."""
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
        for word in WAKE_WORDS:
            if word in text:
                return True
        return False

    def _loop(self):
        print("[Voice] Calibrating... please wait.")
        time.sleep(1)
        print("[Voice] Listening for wake word...")

        while self.running:
            try:
                # Record a short chunk to check for wake word
                raw = self._record(seconds=3)
                text = self._transcribe(raw)

                if not text:
                    continue

                print(f"[Voice] Heard: {text}")

                if self._is_wake_word(text):
                    print("[Voice] Wake word detected!")
                    self.on_wake()

                    # Now record the command
                    print("[Voice] Listening for command...")
                    cmd_raw = self._record(seconds=5)
                    command = self._transcribe(cmd_raw)

                    if command:
                        # Strip the wake word from command if present
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
    print("Say 'Hey JARVIS' followed by a command.")
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