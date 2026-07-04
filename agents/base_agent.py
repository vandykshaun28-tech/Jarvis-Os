"""
base_agent.py
─────────────
Foundation for all JARVIS background agents.

An agent is a named worker that runs its `tick()` on an interval in a
daemon thread, keeps a rolling event log, and can talk to Shaun through
the brain's chat/voice callbacks. Everything is exception-proof: a
crashing tick marks the agent 'error' and keeps the loop alive.
"""

import threading
import time
from collections import deque
from datetime import datetime


class BaseAgent:

    name        = "agent"
    description = ""

    def __init__(self, brain=None, interval_seconds=60):
        self.brain    = brain
        self.interval = interval_seconds
        self.status   = "stopped"      # stopped | running | error | not_configured
        self.last_run = None
        self.last_message = ""
        self.events   = deque(maxlen=60)
        self._stop    = threading.Event()
        self._thread  = None
        self._lock    = threading.Lock()

    # ── lifecycle ───────────────────────────────
    def start(self):
        if self._thread and self._thread.is_alive():
            if self._stop.is_set():
                # was just stopped and the thread hasn't wound down yet —
                # simply un-stop it and let the loop carry on
                self._stop.clear()
                self.status = "running"
                self.log(f"{self.name} restarted.")
                return f"{self.name} restarted."
            return f"{self.name} is already running."
        self._stop.clear()
        self.status = "running"
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name=f"agent-{self.name}")
        self._thread.start()
        self.log(f"{self.name} started.")
        return f"{self.name} started."

    def stop(self):
        self._stop.set()
        self.status = "stopped"
        self.log(f"{self.name} stopped.")
        return f"{self.name} stopped."

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() \
            and not self._stop.is_set()

    def _loop(self):
        # small initial stagger so all agents don't fire at once
        self._sleep(3)
        while not self._stop.is_set():
            try:
                self.tick()
                if self.status == "error":
                    self.status = "running"
            except Exception as e:
                self.status = "error"
                self.log(f"error: {e}")
            self.last_run = datetime.now()
            self._sleep(self.interval)

    def _sleep(self, seconds):
        """Interruptible sleep — reacts to stop() within a second."""
        end = time.time() + seconds
        while time.time() < end and not self._stop.is_set():
            time.sleep(1)

    # ── override me ─────────────────────────────
    def tick(self):
        pass

    # ── reporting ───────────────────────────────
    def log(self, message):
        with self._lock:
            self.events.appendleft(
                (datetime.now().strftime("%H:%M:%S"), str(message)))
        self.last_message = str(message)

    def say(self, message, speak=False):
        """Log + push to the JARVIS console (and optionally voice)."""
        self.log(message)
        b = self.brain
        if b is not None:
            cb = getattr(b, "chat_callback", None)
            if cb:
                try: cb(f"[{self.name}] {message}")
                except Exception: pass
            if speak:
                vc = getattr(b, "voice_callback", None)
                if vc:
                    try: vc(message)
                    except Exception: pass

    def snapshot(self):
        with self._lock:
            events = list(self.events)[:12]
        return {
            "name":         self.name,
            "description":  self.description,
            "status":       self.status if self.running or self.status in
                            ("not_configured", "error") else "stopped",
            "last_run":     self.last_run.strftime("%H:%M:%S") if self.last_run else "—",
            "last_message": self.last_message,
            "events":       events,
        }
