"""
core/worker.py
──────────────
Runs the brain inside the worker thread.

Two fixes over the old hud/worker.py:

1. The brain used to be loaded in Worker.__init__, which ran on the
   MAIN (GUI) thread before moveToThread — so the whole window froze
   while Anthropic/Obsidian/etc. started up. Now `initialize()` is
   invoked in the worker thread after the thread starts, and the UI
   appears instantly while the brain boots in the background.

2. The old HUD injected chat/voice callbacks with a 3-second timer and
   hoped the brain was loaded by then (a race). Now the worker emits
   `ready` when the brain is actually up, and wires the callbacks
   itself at that moment.
"""

import os
import importlib.util

from PySide6.QtCore import QObject, Signal, Slot


def _load_brain():
    brain_path = os.path.join(
        os.path.dirname(__file__), '..', 'brain', 'brain.py'
    )
    brain_path = os.path.abspath(brain_path)
    spec   = importlib.util.spec_from_file_location("JarvisBrainModule", brain_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JarvisBrain()


class Worker(QObject):

    finished = Signal(str)   # a reply to show in the console
    progress = Signal(str)   # live status updates (research progress, reminders, ...)
    ready    = Signal()      # brain finished loading

    def __init__(self):
        super().__init__()
        self.brain = None
        self._load_error = None
        # Optional: set by the controller BEFORE the thread starts.
        # fn(text) that speaks — must be thread-safe (JarvisVoice.speak is).
        self.voice_speak = None

    @Slot()
    def initialize(self):
        """Runs in the worker thread (connected to QThread.started)."""
        try:
            self.brain = _load_brain()
            self._wire_callbacks()
            print("[Worker] Brain loaded successfully.")
            self.ready.emit()
            # Pocket JARVIS — phone chats with THIS same brain
            try:
                from core.phone_server import start_phone_server
                url = start_phone_server(self.brain)
                if url:
                    self.progress.emit(
                        f"[Phone] Pocket JARVIS is live, sir — open {url} "
                        f"on your phone (same Wi-Fi) and enter your key.")
            except Exception as e:
                print(f"[Phone] server failed: {e}")
        except Exception as e:
            self._load_error = str(e)
            import traceback
            traceback.print_exc()
            self.progress.emit(f"Brain failed to load: {e}")

    def _wire_callbacks(self):
        """Give every brain subsystem a live line to the UI (and voice)."""
        brain = self.brain
        if brain is None:
            return
        brain.chat_callback  = self.progress.emit
        brain.voice_callback = self.voice_speak
        for sub in ("researcher", "research_agent", "tasks", "agent"):
            obj = getattr(brain, sub, None)
            if obj is None:
                continue
            if hasattr(obj, "on_progress"):
                obj.on_progress = self.progress.emit
            if hasattr(obj, "on_update"):
                obj.on_update = self.progress.emit
            if hasattr(obj, "chat_callback"):
                obj.chat_callback = self.progress.emit
            if hasattr(obj, "voice_callback"):
                obj.voice_callback = self.voice_speak

    @Slot()
    def shutdown_browser(self):
        """Close Playwright IN THIS (worker) thread — it was created here,
        and tearing it down from the GUI thread on exit is what threw the
        'Timers cannot be stopped from another thread' / EPIPE errors."""
        b = getattr(self.brain, "browser", None) if self.brain else None
        if b is not None:
            try:
                b.close()
            except Exception:
                pass

    @Slot(str)
    def process(self, text: str):
        if self.brain is None:
            if self._load_error:
                self.finished.emit(f"Brain not available: {self._load_error}")
            else:
                self.finished.emit("One moment, sir — still starting up.")
            return
        try:
            files = None
            if text.startswith('{"__jarvis_files__"'):
                import json
                try:
                    payload = json.loads(text)
                    text  = payload.get("text", "")
                    files = payload.get("files") or None
                except Exception:
                    pass
            reply = self.brain.process(text, files=files)
            self.finished.emit(reply)
        except Exception as e:
            print(f"[Worker] Error: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit(f"System error: {e}")
