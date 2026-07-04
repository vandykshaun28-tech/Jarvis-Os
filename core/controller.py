"""
core/controller.py
──────────────────
Glue between the v20 UI, the brain (worker thread), and voice.

Voice was previously only wired into the old hud/hud.py app. It now
lives here, so the v20 UI has:
  - wake-word listening ("hey jarvis") → command → brain
  - spoken replies (TTS)
  - the microphone MUTED while JARVIS speaks, so he no longer hears
    and reacts to his own voice.
"""

from PySide6.QtCore import (
    QObject,
    Signal,
    QThread,
    Slot,
    Qt,
    QMetaObject,
    Q_ARG,
)

from core.worker import Worker

VOICE_ERR = LISTENER_ERR = None

try:
    from voice.voice import JarvisVoice
    VOICE_OK = True
except Exception as _e:
    VOICE_ERR = str(_e)
    print(f"[Controller] TTS unavailable: {_e}")
    VOICE_OK = False

try:
    from voice.voice_listener import VoiceListener, device_report
    LISTENER_OK = True
except Exception as _e:
    LISTENER_ERR = str(_e)
    print(f"[Controller] Voice listener unavailable: {_e}")
    LISTENER_OK = False
    def device_report():
        return "  (voice packages not installed)"


class JarvisController(QObject):

    # -------------------------
    # Signals to UI
    # -------------------------

    responseReceived   = Signal(str)
    userMessage        = Signal(str)
    statusChanged      = Signal(str)
    processingStarted  = Signal()
    processingFinished = Signal()
    errorOccurred      = Signal(str)
    progressReceived   = Signal(str)   # live brain updates (research, reminders)
    voiceHeard         = Signal(str)   # a spoken command, for the console log
    brainReady         = Signal()
    cameraPanel        = Signal(bool)  # True = show the live mini tab

    # internal: safe hand-off from listener thread → Qt main thread
    _voiceCommand = Signal(str)
    _wakeDetected = Signal()

    # -----------------------------------------------------

    def __init__(self):

        super().__init__()

        self.busy = False

        self.startup_notes = []   # shown in the console once the UI is up

        # ── Voice output (TTS) ────────────────────────────
        self.voice = None
        self._voice_err = VOICE_ERR
        if VOICE_OK:
            try:
                self.voice = JarvisVoice(
                    on_speaking_start=self._mute_mic,
                    on_speaking_end=self._unmute_mic,
                )
            except Exception as e:
                self._voice_err = str(e)
                print(f"[Controller] TTS init failed: {e}")

        # ── Brain in worker thread ────────────────────────
        self.thread = QThread()
        self.worker = Worker()
        if self.voice:
            self.worker.voice_speak = self.voice.speak  # queue-based, thread-safe
        self.worker.moveToThread(self.thread)

        # Load the brain IN the worker thread once it starts,
        # so the UI never freezes during startup.
        self.thread.started.connect(self.worker.initialize)
        self.worker.finished.connect(self._worker_finished)
        self.worker.progress.connect(self.progressReceived)
        self.worker.ready.connect(self._brain_ready)

        self.thread.start()

        # ── Voice input (wake word + commands) ────────────
        self.listener = None
        self._listener_err = LISTENER_ERR
        self._voiceCommand.connect(self._on_voice_command)
        self._wakeDetected.connect(self._on_wake)
        if LISTENER_OK:
            try:
                self.listener = VoiceListener(
                    on_command=self._voiceCommand.emit,
                    on_wake=self._wakeDetected.emit,
                )
                self.listener.start()
                print("[Controller] Voice listener started.")
            except Exception as e:
                self._listener_err = str(e)
                print(f"[Controller] Listener init failed: {e}")

        # Startup diagnostics for the console — no more silent failures.
        if self.voice:
            self.startup_notes.append(
                f"Voice output: {self.voice.engine} engine ready.")
        else:
            self.startup_notes.append(
                f"Voice output OFFLINE: {self._voice_err or 'unknown error'}")
        if self.listener:
            self.startup_notes.append(
                "Microphone: listening for 'hey jarvis'. "
                "Type 'voice status' to see devices.")
        else:
            self.startup_notes.append(
                f"Microphone OFFLINE: {self._listener_err or 'unknown error'} "
                f"— try: pip install sounddevice SpeechRecognition numpy")

    # -----------------------------------------------------
    # Mic gating while JARVIS talks (called from voice thread —
    # listener.mute/unmute just flip flags, which is thread-safe).
    # -----------------------------------------------------

    def _mute_mic(self):
        if self.listener:
            try:
                self.listener.mute()
            except Exception:
                pass

    def _unmute_mic(self):
        if self.listener:
            try:
                self.listener.unmute()
            except Exception:
                pass

    # -----------------------------------------------------

    @Slot()
    def _brain_ready(self):
        self.statusChanged.emit("Ready")
        self.brainReady.emit()

    @Slot()
    def _on_wake(self):
        self.statusChanged.emit("Listening...")

    @Slot(str)
    def _on_voice_command(self, text):
        self.voiceHeard.emit(text)
        self.ask(text)

    # -----------------------------------------------------

    def voice_status(self) -> str:
        lines = []
        if self.voice:
            lines.append(f"Voice output: ONLINE ({self.voice.engine} engine).")
        else:
            lines.append(f"Voice output: OFFLINE — {self._voice_err}")
        if self.listener:
            lines.append("Microphone: ONLINE, waiting for 'hey jarvis'.")
        else:
            lines.append(f"Microphone: OFFLINE — {self._listener_err}")
        lines.append("Input devices:")
        lines.append(device_report())
        lines.append("If the wrong device is 'in use', set MIC_DEVICE_INDEX "
                     "in config.py to the right number and restart.")
        return "\n".join(lines)

    @Slot(str, list)
    def ask_with_files(self, text, files):
        """Console drag & drop — wraps the message and file paths into a
        JSON envelope the worker unpacks in its own thread."""
        import json as _json
        payload = _json.dumps({"__jarvis_files__": True,
                               "text": text, "files": list(files)})
        self.ask(payload, _display=text)

    @Slot(str)
    def ask(self, text, _display=None):

        text = text.strip()

        if not text:
            return

        # answered locally — the brain can't see the mic hardware
        if text.lower() in ("voice status", "mic status", "microphone status"):
            self.responseReceived.emit(self.voice_status())
            return

        # camera mini tab — UI-level commands, no brain round-trip.
        # Fuzzy on purpose: "close camera mini tab", "hide the vision
        # window", "shut the camera view" all count.
        low = text.lower().strip(" .!?")
        cam_words = ("camera", "mini tab", "minitab", "vision", "cam view")
        if any(w in low for w in cam_words) and len(low.split()) <= 8:
            if any(w in low for w in ("close", "hide", "shut", "dismiss",
                                       "kill", "stop", "off")):
                self.cameraPanel.emit(False)
                self.responseReceived.emit("Camera view closed, sir.")
                return
            if any(w in low for w in ("show", "open", "display", "bring up",
                                       "pop up", "view", "see live", "on")):
                self.cameraPanel.emit(True)
                self.responseReceived.emit("Camera view open, sir.")
                return

        if self.busy:
            self.errorOccurred.emit("Already processing...")
            return

        self.busy = True

        self.userMessage.emit(text)
        self.statusChanged.emit("Thinking...")
        self.processingStarted.emit()

        # Execute Worker.process() INSIDE the worker thread.
        QMetaObject.invokeMethod(
            self.worker,
            "process",
            Qt.QueuedConnection,
            Q_ARG(str, text),
        )

    # -----------------------------------------------------

    @Slot(str)
    def _worker_finished(self, reply):

        self.busy = False

        self.statusChanged.emit("Ready")
        self.processingFinished.emit()
        self.responseReceived.emit(reply)

        if self.voice and reply:
            self.voice.speak(reply)

    # -----------------------------------------------------
    # Read-only accessors for UI pages (safe cross-thread:
    # they only read plain-data snapshots guarded by locks).
    # -----------------------------------------------------

    def agent_snapshots(self):
        b = getattr(self.worker, "brain", None)
        mgr = getattr(b, "agent_manager", None) if b else None
        return mgr.snapshot() if mgr else []

    def get_agent(self, name):
        b = getattr(self.worker, "brain", None)
        mgr = getattr(b, "agent_manager", None) if b else None
        return mgr.get(name) if mgr else None

    # -----------------------------------------------------

    def shutdown(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        if self.voice:
            try:
                self.voice.shutdown()
            except Exception:
                pass
        self.thread.quit()
        self.thread.wait()
