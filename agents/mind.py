"""
mind.py
───────
JARVIS's inner voice — the part that thinks when nobody is talking
to him.

Every cycle it gathers the situation (time of day, pending tasks,
reminders, what the other agents have seen, research queue) and asks
Claude to decide, as JARVIS, whether anything deserves action:
say something to Shaun, quietly queue background research, or stay
silent. Most cycles it should conclude that silence is right — a
good butler doesn't narrate the furniture.
"""

import json
import re
from datetime import datetime

import config
from agents.base_agent import BaseAgent


class Mind(BaseAgent):

    name        = "Mind"
    description = "Autonomous thinking cycle"

    def __init__(self, brain=None):
        super().__init__(brain=brain,
                         interval_seconds=config.MIND_INTERVAL_MINUTES * 60)
        self._last_thought = ""

    def _quiet_hours(self):
        h = datetime.now().hour
        s, e = config.MIND_QUIET_START, config.MIND_QUIET_END
        return h >= s or h < e if s > e else s <= h < e

    def _situation(self):
        b = self.brain
        now = datetime.now()
        parts = [f"Time: {now.strftime('%A %H:%M')}"]
        try:
            if b.tasks:
                pending = b.tasks.count_pending()
                parts.append(f"Pending tasks: {pending}")
                if pending:
                    parts.append(b.tasks.list_pending()[:400])
        except Exception: pass
        try:
            if b.researcher:
                parts.append(f"Knowledge topics: {len(b.researcher.knowledge)}")
                parts.append("Researcher busy" if b.researcher.active else "Researcher idle")
        except Exception: pass
        try:
            mgr = getattr(b, "agent_manager", None)
            if mgr:
                for snap in mgr.snapshot():
                    if snap["name"] == self.name:
                        continue
                    ev = "; ".join(m for _, m in snap["events"][:3])
                    parts.append(f"Agent {snap['name']} [{snap['status']}]: {ev[:200]}")
        except Exception: pass
        if self._last_thought:
            parts.append(f"Your previous cycle's thought: {self._last_thought[:200]}")
        return "\n".join(parts)

    def tick(self):
        b = self.brain
        if b is None or getattr(b, "llm", None) is None:
            return
        situation = self._situation()
        try:
            raw = b.llm.simple(
                user=situation,
                max_tokens=300,
                system=(
                    "You are the inner voice of Allison, Shaun Van Dyk's AI. "
                    "You wake every so often, look at the situation, and decide "
                    "if anything is genuinely worth acting on. You CANNOT build, "
                    "code, 'work on' or STUDY anything on your own — your only "
                    "power is speaking ONE short message when it truly helps. "
                    "Never tell Shaun you are building, studying or will study "
                    "something; you only study when he explicitly asks. "
                    "Be very selective: "
                    "speak only when useful (an overdue task at a sensible hour, "
                    "something notable from the Shopify or Trading agents, a "
                    "morning heads-up). Never repeat what was already said in a "
                    "previous cycle. Most cycles the right answer is silence.\n"
                    "Reply with ONLY a JSON object: "
                    '{"speak": "<short message to Shaun>" or null, '
                    '"thought": "<one-line private note to your next cycle>"}'
                ),
            )
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            decision = json.loads(m.group(0)) if m else {}
        except Exception as e:
            self.log(f"thinking failed: {e}")
            return

        self._last_thought = decision.get("thought") or ""
        self.log(f"thought: {self._last_thought or '(none)'}")

        msg = decision.get("speak")
        if msg and not self._quiet_hours():
            self.say(msg, speak=True)

        topic = decision.get("research")
        if topic:
            try:
                if b.researcher and not b.researcher.active:
                    b.researcher.study_async(topic, depth=8)
                    self.log(f"queued research: {topic}")
            except Exception as e:
                self.log(f"research queue failed: {e}")
