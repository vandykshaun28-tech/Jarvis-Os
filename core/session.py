"""
core/session.py — one conversation, many windows.

THE ARCHITECTURE THIS ENFORCES:
    Allison is a single persistent assistant. The PC dashboard and the
    phone are two thin windows onto her, not two assistants that happen
    to share a brain object.

Before this, both surfaces called the same brain — so memory and tools
were genuinely shared — but each rendered its OWN local list of
messages. Say something on the phone and the desk console never heard
it; ask the desk for a photo and the phone's log had a hole in it. Two
transcripts of one conversation, neither complete.

Now every message from every device lands here, in order, with an id.
Devices do not keep their own log; they render a view of this one.

  • In-process listeners (the PC UI) get a callback the moment a message
    lands, so a phone message appears on the desk without a refresh.
  • Remote clients (the phone) poll since(cursor) and receive anything
    they have not seen. A cursor is monotonic, so nothing is missed and
    nothing arrives twice.

Thread safety matters here: Flask serves the phone on its own threads
while Qt owns the desktop. Every mutation takes the lock, and callbacks
fire outside it so a slow listener cannot stall a request.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

MAX_IN_MEMORY = 400          # transcript kept for replay/joining devices
MAX_ON_DISK = 200


class SharedSession:

    def __init__(self, path=None):
        self._lock = threading.RLock()
        self._subs = []
        self._next_id = 1
        self.messages = []
        self.status = {
            "state": "standing_by",     # standing_by | listening | working
            "activity": "",
            "since": time.time(),
        }
        self.path = Path(path) if path else None
        self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _load(self):
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.messages = data.get("messages", [])[-MAX_ON_DISK:]
            self._next_id = max((m.get("id", 0) for m in self.messages),
                                default=0) + 1
        except Exception as e:
            print(f"[Session] could not load transcript: {e}")

    def save(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(
                {"messages": self.messages[-MAX_ON_DISK:]},
                indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Session] could not save transcript: {e}")

    # ── writing ──────────────────────────────────────────────────────

    def append(self, role, text, source="pc", kind="text", extra=None):
        """Add a message. `source` is which window it came FROM, so a
        device can style its own messages differently without needing a
        separate log. Returns the stored message."""
        text = "" if text is None else str(text)
        with self._lock:
            msg = {
                "id": self._next_id,
                "ts": time.time(),
                "time": datetime.now().strftime("%H:%M"),
                "role": role,             # user | allison | system | tool
                "text": text,
                "source": source,         # pc | phone | voice | agent
                "kind": kind,             # text | image | panel
            }
            if extra:
                msg.update(extra)
            self._next_id += 1
            self.messages.append(msg)
            if len(self.messages) > MAX_IN_MEMORY:
                self.messages = self.messages[-MAX_IN_MEMORY:]
            subs = list(self._subs)
        # fire OUTSIDE the lock — a slow UI listener must not block the
        # phone's HTTP thread, and vice versa
        for fn in subs:
            try:
                fn(msg)
            except Exception as e:
                print(f"[Session] listener failed: {e}")
        self.save()
        return msg

    def set_status(self, state=None, activity=None):
        with self._lock:
            if state is not None:
                self.status["state"] = state
            if activity is not None:
                self.status["activity"] = activity
            self.status["since"] = time.time()
            return dict(self.status)

    # ── reading ──────────────────────────────────────────────────────

    def since(self, cursor=0, limit=60):
        """Messages newer than `cursor`, plus the new cursor.

        A joining device passes 0 and gets recent history, so opening the
        phone shows the conversation already in progress rather than a
        blank page pretending nothing has happened.
        """
        try:
            cursor = int(cursor)
        except Exception:
            cursor = 0
        with self._lock:
            if cursor <= 0:
                out = self.messages[-limit:]
            else:
                out = [m for m in self.messages if m["id"] > cursor][:limit]
            newest = self.messages[-1]["id"] if self.messages else 0
            return {
                "messages": out,
                "cursor": max(newest, cursor),
                "status": dict(self.status),
            }

    def recent(self, n=40):
        with self._lock:
            return list(self.messages[-n:])

    # ── live listeners (in-process, i.e. the PC UI) ──────────────────

    def subscribe(self, fn):
        """fn(msg) is called for every new message from ANY device."""
        with self._lock:
            if fn not in self._subs:
                self._subs.append(fn)
        return fn

    def unsubscribe(self, fn):
        with self._lock:
            if fn in self._subs:
                self._subs.remove(fn)
