"""
task_manager.py
───────────────
JARVIS autonomous task engine.
Location: C:\jarvis_v18\brain\task_manager.py

Handles:
- Task creation and tracking
- Scheduled reminders
- Multi-step workflows
- Autonomous execution
"""

import os
import json
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


TASKS_FILE = Path(r"C:\jarvis_v18\memory\tasks.json")


class Task:
    def __init__(self, title, description="", priority="normal",
                 due=None, steps=None, tags=None):
        self.id          = datetime.now().strftime("%Y%m%d%H%M%S")
        self.title       = title
        self.description = description
        self.priority    = priority
        self.due         = due
        self.steps       = steps or []
        self.tags        = tags or []
        self.status      = "pending"
        self.created     = datetime.now().isoformat()
        self.completed   = None

    def to_dict(self):
        return self.__dict__

    @classmethod
    def from_dict(cls, d):
        t = cls(d["title"])
        t.__dict__.update(d)
        return t


class TaskManager:

    def __init__(self, voice_callback=None, chat_callback=None):
        self.voice_callback = voice_callback  # fn(text) to speak
        self.chat_callback  = chat_callback   # fn(text) to show in chat
        self.tasks = []
        self.reminders = []
        self._load()
        self._start_scheduler()
        print("[Tasks] Task manager online.")

    # ── PERSISTENCE ─────────────────────────────

    def _load(self):
        try:
            if TASKS_FILE.exists():
                data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
                self.tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
                print(f"[Tasks] Loaded {len(self.tasks)} tasks.")
        except Exception as e:
            print(f"[Tasks] Load error: {e}")
            self.tasks = []

    def _save(self):
        try:
            TASKS_FILE.parent.mkdir(exist_ok=True)
            data = {"tasks": [t.to_dict() for t in self.tasks]}
            TASKS_FILE.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Tasks] Save error: {e}")

    # ── TASK CRUD ────────────────────────────────

    def add(self, title: str, description: str = "",
            priority: str = "normal", due: str = None) -> str:
        task = Task(title, description, priority, due)
        self.tasks.append(task)
        self._save()
        return f"Task added: {title}"

    def complete(self, search: str) -> str:
        for t in self.tasks:
            if search.lower() in t.title.lower() and t.status == "pending":
                t.status    = "done"
                t.completed = datetime.now().isoformat()
                self._save()
                return f"Task completed: {t.title}"
        return f"No pending task found matching '{search}'."

    def delete(self, search: str) -> str:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks
                      if search.lower() not in t.title.lower()]
        self._save()
        removed = before - len(self.tasks)
        return f"Removed {removed} task(s) matching '{search}'."

    def list_pending(self) -> str:
        pending = [t for t in self.tasks if t.status == "pending"]
        if not pending:
            return "No pending tasks, sir."
        lines = [f"- [{t.priority.upper()}] {t.title}" for t in pending]
        return f"You have {len(pending)} pending tasks:\n" + "\n".join(lines)

    def list_all(self) -> str:
        if not self.tasks:
            return "No tasks found, sir."
        lines = []
        for t in self.tasks:
            icon = "✓" if t.status == "done" else "○"
            lines.append(f"{icon} [{t.priority}] {t.title}")
        return "\n".join(lines)

    def count_pending(self) -> int:
        return len([t for t in self.tasks if t.status == "pending"])

    # ── REMINDERS ───────────────────────────────

    def remind_in(self, minutes: int, message: str):
        """Set a reminder for X minutes from now."""
        fire_at = datetime.now() + timedelta(minutes=minutes)
        self.reminders.append({"fire_at": fire_at, "message": message})
        return f"Reminder set for {minutes} minutes from now, sir."

    def remind_at(self, time_str: str, message: str):
        """Set a reminder for a specific time e.g. '14:30'."""
        try:
            now = datetime.now()
            hour, minute = map(int, time_str.split(":"))
            fire_at = now.replace(hour=hour, minute=minute, second=0)
            if fire_at < now:
                fire_at += timedelta(days=1)
            self.reminders.append({"fire_at": fire_at, "message": message})
            return f"Reminder set for {time_str}, sir."
        except Exception as e:
            return f"Could not set reminder: {e}"

    # ── SYSTEM ACTIONS ───────────────────────────

    def open_app(self, app: str) -> str:
        apps = {
            "notepad":    "notepad",
            "calculator": "calc",
            "chrome":     "start chrome",
            "obsidian":   "start obsidian://open",
            "explorer":   "explorer",
            "terminal":   "start cmd",
            "vs code":    "code",
            "spotify":    "start spotify",
        }
        cmd = apps.get(app.lower())
        if cmd:
            os.system(cmd)
            return f"Opening {app}, sir."
        return f"I don't know how to open {app}, sir."

    def search_files(self, query: str, path: str = "C:\\") -> str:
        try:
            results = []
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith(".")] [:3]
                for f in files:
                    if query.lower() in f.lower():
                        results.append(os.path.join(root, f))
                if len(results) >= 5:
                    break
            if results:
                return "Found:\n" + "\n".join(results[:5])
            return f"No files found matching '{query}', sir."
        except Exception as e:
            return f"Search error: {e}"

    # ── SCHEDULER ───────────────────────────────

    def _start_scheduler(self):
        t = threading.Thread(target=self._scheduler_loop, daemon=True)
        t.start()

    def _scheduler_loop(self):
        import time
        while True:
            now = datetime.now()
            fired = []
            for r in self.reminders:
                if now >= r["fire_at"]:
                    msg = f"Reminder, sir: {r['message']}"
                    if self.voice_callback:
                        self.voice_callback(msg)
                    if self.chat_callback:
                        self.chat_callback(msg)
                    fired.append(r)
            for r in fired:
                self.reminders.remove(r)
            time.sleep(15)