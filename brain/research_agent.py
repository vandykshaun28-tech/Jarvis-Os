"""
research_agent.py
─────────────────
JARVIS Background Research Agent.
Location: C:\jarvis_v18\brain\research_agent.py

Queues multiple topics and studies them autonomously
in the background while JARVIS stays fully responsive.

Commands:
    "research agent study: topic1, topic2, topic3"
    "research agent status"
    "research agent stop"
    "research agent queue"
"""

import os
import sys
import threading
import queue
import time
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

QUEUE_FILE = config.RESEARCH_QUEUE_FILE


class ResearchAgent:

    def __init__(self, researcher, on_update=None, on_complete=None):
        self.researcher  = researcher        # The Researcher instance from brain
        self.on_update   = on_update         # fn(msg) — live chat updates
        self.on_complete = on_complete       # fn(msg) — topic complete
        self.queue       = []                # List of pending topics
        self.completed   = []                # List of completed topics
        self.failed      = []                # List of failed topics
        self.current     = None              # Topic currently being studied
        self.running     = False             # Is agent active
        self.paused      = False             # Is agent paused
        self._thread     = None
        self._load_queue()
        print("[ResearchAgent] Background research agent ready.")

    # ── PERSISTENCE ─────────────────────────────

    def _load_queue(self):
        """Load saved queue from previous session."""
        try:
            if QUEUE_FILE.exists():
                data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
                self.queue     = data.get("queue", [])
                self.completed = data.get("completed", [])
                if self.queue:
                    print(f"[ResearchAgent] Loaded {len(self.queue)} pending topics.")
        except Exception as e:
            print(f"[ResearchAgent] Queue load error: {e}")

    def _save_queue(self):
        """Save queue state so it survives restarts."""
        try:
            QUEUE_FILE.parent.mkdir(exist_ok=True)
            data = {
                "queue":     self.queue,
                "completed": self.completed,
                "failed":    self.failed,
                "saved_at":  datetime.now().isoformat(),
            }
            QUEUE_FILE.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[ResearchAgent] Queue save error: {e}")

    # ── PUBLIC API ───────────────────────────────

    def add_topics(self, topics: list) -> str:
        """Add multiple topics to the research queue."""
        added = []
        skipped = []

        for topic in topics:
            topic = topic.strip().strip("\"'")
            if not topic:
                continue
            # Skip if already studied
            if topic.lower() in [k.lower() for k in self.researcher.knowledge]:
                skipped.append(topic)
                continue
            # Skip if already in queue
            if topic.lower() in [q.lower() for q in self.queue]:
                skipped.append(topic)
                continue
            self.queue.append(topic)
            added.append(topic)

        self._save_queue()

        result = ""
        if added:
            result += f"Added {len(added)} topics to research queue: {', '.join(added)}. "
        if skipped:
            result += f"Skipped {len(skipped)} already known topics: {', '.join(skipped)}. "

        if added and not self.running:
            self.start()
            result += "Research agent is now running in the background, sir."

        return result if result else "No new topics to add, sir."

    def start(self):
        """Start the background research loop."""
        if self.running:
            return
        self.running = True
        self.paused  = False
        self._thread = threading.Thread(
            target=self._research_loop,
            daemon=True
        )
        self._thread.start()
        self._update(f"Research agent started. {len(self.queue)} topics in queue.")

    def stop(self):
        """Stop the research agent after current topic."""
        self.running = False
        self._update("Research agent stopping after current topic completes, sir.")

    def pause(self):
        """Pause between topics."""
        self.paused = True
        self._update("Research agent paused, sir.")

    def resume(self):
        """Resume paused agent."""
        self.paused = False
        self._update("Research agent resumed, sir.")

    def clear_queue(self):
        """Clear all pending topics."""
        count = len(self.queue)
        self.queue = []
        self._save_queue()
        return f"Cleared {count} topics from queue, sir."

    def status(self) -> str:
        """Return current agent status."""
        if not self.running and not self.queue:
            status = "idle"
        elif self.paused:
            status = "paused"
        elif self.running:
            status = "active"
        else:
            status = "stopped"

        lines = [f"Research Agent: {status.upper()}"]

        if self.current:
            lines.append(f"Currently studying: {self.current}")

        if self.queue:
            lines.append(f"Queue ({len(self.queue)} topics):")
            for i, t in enumerate(self.queue[:5], 1):
                lines.append(f"  {i}. {t}")
            if len(self.queue) > 5:
                lines.append(f"  ... and {len(self.queue)-5} more")

        if self.completed:
            lines.append(f"Completed this session: {', '.join(self.completed[-5:])}")

        if self.failed:
            lines.append(f"Failed: {', '.join(self.failed)}")

        total = len(self.researcher.knowledge)
        lines.append(f"Total knowledge base: {total} topics")

        return "\n".join(lines)

    def get_queue(self) -> str:
        """List queued topics."""
        if not self.queue:
            return "Research queue is empty, sir."
        lines = ["Queued topics:"]
        for i, t in enumerate(self.queue, 1):
            lines.append(f"  {i}. {t}")
        return "\n".join(lines)

    # ── INTERNAL LOOP ────────────────────────────

    def _research_loop(self):
        """Main background loop — processes queue one topic at a time."""
        self._update("Research agent online. Starting queue...")

        while self.running:
            # Wait if paused
            while self.paused and self.running:
                time.sleep(2)

            # Get next topic
            if not self.queue:
                self._update(
                    f"Research queue complete, sir. "
                    f"Studied {len(self.completed)} topics this session. "
                    f"Total knowledge base: {len(self.researcher.knowledge)} topics."
                )
                self.running = False
                self.current = None
                self._save_queue()
                break

            topic = self.queue[0]
            self.current = topic
            self._save_queue()

            self._update(
                f"Research agent starting: '{topic}' "
                f"({len(self.queue)} topics remaining in queue)..."
            )

            # Set up progress reporting
            self.researcher.on_progress = self._on_progress
            self.researcher.on_complete = self._on_topic_complete

            try:
                # Study synchronously inside this thread
                self.researcher._study(topic, depth=12)
                self.completed.append(topic)
                if topic in self.queue:
                    self.queue.remove(topic)
            except Exception as e:
                self._update(f"Research failed for '{topic}': {e}")
                self.failed.append(topic)
                if topic in self.queue:
                    self.queue.remove(topic)
            finally:
                self.current = None
                self._save_queue()

            # Brief pause between topics to avoid rate limiting
            if self.queue and self.running:
                self._update(f"Resting 5 seconds before next topic...")
                time.sleep(5)

        self.running = False
        print("[ResearchAgent] Loop complete.")

    def _on_progress(self, msg: str):
        self._update(msg)

    def _on_topic_complete(self, msg: str):
        if self.on_complete:
            self.on_complete(msg)
        remaining = len(self.queue)
        if remaining > 0:
            self._update(
                f"Topic complete. {remaining} topics remaining in queue. "
                f"Next: {self.queue[0] if self.queue else 'none'}"
            )

    def _update(self, msg: str):
        """Send update to chat."""
        print(f"[ResearchAgent] {msg}")
        if self.on_update:
            self.on_update(f"🤖 {msg}")