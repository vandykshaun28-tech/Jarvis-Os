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
    voiceMuteChanged   = Signal(bool)  # True = JARVIS's voice is muted
    listeningChanged   = Signal(bool)  # True = actively capturing a command
    miniModeChanged    = Signal(bool)  # True = shrink to corner chat box
    # a message that arrived from the OTHER window (the phone), so the
    # desk console can show it live instead of the two logs diverging
    remoteMessage      = Signal(str, str)   # (role, text)

    # internal: safe hand-off from listener thread → Qt main thread
    _voiceCommand = Signal(str)
    _wakeDetected = Signal()
    _listenIdle   = Signal()

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
        self._listenIdle.connect(self._on_listen_idle)
        if LISTENER_OK:
            try:
                self.listener = VoiceListener(
                    on_command=self._voiceCommand.emit,
                    on_wake=self._wakeDetected.emit,
                    on_idle=self._listenIdle.emit,
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
        # ── LISTEN TO THE SHARED TRANSCRIPT ──────────────────────────
        # The phone writes to the same session object. Emitting a Qt
        # signal here is what makes the hand-off thread-safe: the
        # callback fires on Flask's thread, and Qt marshals delivery
        # onto the UI thread for us. Touching widgets directly from
        # that callback would be a crash waiting to happen.
        try:
            brain = getattr(self.worker, "brain", None) or \
                getattr(self, "brain", None)
            sess = getattr(brain, "session", None)
            if sess is not None:
                def _on_remote(msg):
                    try:
                        if msg.get("source") == "phone":
                            self.remoteMessage.emit(
                                str(msg.get("role", "")),
                                str(msg.get("text", "")))
                    except Exception:
                        pass
                sess.subscribe(_on_remote)
                self._session_sub = _on_remote      # keep a reference
                print("[Controller] desk is listening to the shared session")
        except Exception as e:
            print(f"[Controller] shared session subscribe failed: {e}")
        # apply persisted user settings now that voice/listener exist
        try:
            from core import settings as user_settings
            if not user_settings.get("voice_enabled", True):
                self.set_voice_muted(True)
            if not user_settings.get("wake_word_enabled", True) \
                    and self.listener:
                self.listener.mute()
        except Exception as e:
            print(f"[Controller] settings apply: {e}")

    @Slot()
    def _on_wake(self):
        self.statusChanged.emit("Listening...")
        self.listeningChanged.emit(True)

    @Slot()
    def _on_listen_idle(self):
        """Wake sequence finished (command captured or timed out)."""
        self.listeningChanged.emit(False)

    @Slot(str)
    def _on_voice_command(self, text):
        self.voiceHeard.emit(text)
        self.ask(text)

    # -----------------------------------------------------

    def set_voice_muted(self, muted: bool):
        if self.voice:
            self.voice.set_muted(muted)
        self.voiceMuteChanged.emit(bool(muted))

    def toggle_voice_mute(self):
        muted = not (self.voice.muted if self.voice else False)
        self.set_voice_muted(muted)

    @Slot()
    def stop_speaking(self):
        """Stop button — cut speech instantly without muting future replies."""
        if self.voice:
            self.voice.stop_now()

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

        # BARGE-IN: the moment Shaun sends ANYTHING new, JARVIS shuts up.
        # No more talking over him while he has moved on.
        if self.voice:
            self.voice.stop_now()

        low = text.lower().strip(" .!?")

        # answered locally — the brain can't see the mic hardware
        if low in ("voice status", "mic status", "microphone status"):
            self.responseReceived.emit(self.voice_status())
            return

        # voice control — stop him mid-sentence or mute/unmute entirely
        if low in ("stop speaking", "stop talking", "be quiet", "quiet",
                   "shut up", "silence", "enough"):
            if self.voice:
                self.voice.stop_now()
            self.responseReceived.emit("Silenced, sir.")
            return
        if low in ("mute yourself", "mute your voice", "go mute",
                   "voice off", "mute jarvis"):
            self.set_voice_muted(True)
            self.responseReceived.emit("Voice muted, sir. I'll keep it in "
                                       "writing until you unmute me.")
            return
        if low in ("unmute yourself", "unmute your voice", "voice on",
                   "you can speak", "speak again", "unmute jarvis"):
            self.set_voice_muted(False)
            self.responseReceived.emit("Voice restored, sir.")
            return

        # window mode — shrink to the corner chat or restore, instantly
        if low in ("mini mode", "go mini", "shrink", "go small",
                   "corner mode", "shrink down"):
            self.miniModeChanged.emit(True)
            self.responseReceived.emit("Going compact, sir.")
            return
        if low in ("full screen", "full mode", "go big", "restore",
                   "maximize", "back to full", "full size"):
            self.miniModeChanged.emit(False)
            self.responseReceived.emit("Back to the full deck, sir.")
            return

        # camera mini tab — UI-level commands, no brain round-trip.
        # Fuzzy on purpose: "close camera mini tab", "hide the vision
        # window", "shut the camera view" all count.
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

    def brain_activity(self):
        """(current_activity, recent entries) — the verified ledger."""
        b = getattr(self.worker, "brain", None)
        if b is None:
            return "starting up", []
        try:
            with b._act_lock:
                entries = list(b.activity)[:12]
            return b.current_activity, entries
        except Exception:
            return "unknown", []

    def get_agent(self, name):
        b = getattr(self.worker, "brain", None)
        mgr = getattr(b, "agent_manager", None) if b else None
        return mgr.get(name) if mgr else None

    def study_progress(self):
        """Live study state {topic, percent, stage, active} so the AI
        Agents page can draw a progress bar Shaun can watch."""
        b = getattr(self.worker, "brain", None)
        if b is None:
            return {"topic": "", "percent": 0, "stage": "", "active": False}
        return getattr(b, "study_progress",
                       {"topic": "", "percent": 0, "stage": "", "active": False})

    def cost_summary(self):
        """(today_cost, month_cost, session_cost) as floats, or zeros
        while the brain is still starting up. Safe to poll from a timer."""
        b = getattr(self.worker, "brain", None)
        ct = getattr(b, "cost_tracker", None) if b else None
        if ct is None:
            return 0.0, 0.0, 0.0
        try:
            return ct.today_cost(), ct.month_cost(), ct.session_summary()["cost"]
        except Exception:
            return 0.0, 0.0, 0.0

    def balance_remaining(self):
        """Credits left (float) or None if the feature is off / brain
        not up yet. Counts down from config.CREDIT_BALANCE_USD."""
        b = getattr(self.worker, "brain", None)
        ct = getattr(b, "cost_tracker", None) if b else None
        if ct is None or not hasattr(ct, "remaining_balance"):
            return None
        try:
            return ct.remaining_balance()
        except Exception:
            return None

    def memory_count(self):
        """How many permanent memories JARVIS holds: saved facts plus
        studied research topics. Drives the gold dots in the brain."""
        b = getattr(self.worker, "brain", None)
        if b is None:
            return 0
        n = 0
        try:
            n += len(b.memory.get_all())
        except Exception:
            pass
        try:
            if b.researcher and getattr(b.researcher, "knowledge", None):
                n += len(b.researcher.knowledge)
        except Exception:
            pass
        return n

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
        # close the browser INSIDE the worker thread (blocking) before we
        # tear the thread down — otherwise Playwright is garbage-collected
        # from the GUI thread and screams about cross-thread timers
        try:
            QMetaObject.invokeMethod(
                self.worker, "shutdown_browser", Qt.BlockingQueuedConnection)
        except Exception:
            pass
        self.thread.quit()
        self.thread.wait()
