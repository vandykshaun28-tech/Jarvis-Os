"""
memory.py — what Allison knows about Shaun.

THE BUG THIS FIXES (found 2026-08-08): the research agent wrote its
findings into the SAME list as personal facts, prefixed "[topic]". Of 43
stored "facts", 36 were nuclear-physics dumps and 7 were about Shaun —
and none of those 7 said what he does for a living. So when he asked for
a website for his turbo business, Allison wrote generic filler about
"high-performance vehicles", because that is genuinely all she had.

Personal memory and researched knowledge are different things and are
now kept apart. Research still gets stored, it just stops drowning the
handful of facts that actually matter.
"""

import json
import os
import re
import shutil

# Research rows look like "[quantum computing] Quantum computers are…"
_RESEARCH_RE = re.compile(r"^\s*\[[^\]]{2,60}\]\s")


class MemoryStore:

    def __init__(self):
        self.memory_file = os.path.join(
            os.path.dirname(__file__), "jarvis_memory.json")
        self.long_term = self.load()
        self._migrate_research_out()

    def load(self):
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        data.setdefault("facts", [])
        data.setdefault("research", [])
        data.setdefault("profile", {})
        return data

    def save(self):
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.long_term, f, indent=4, ensure_ascii=False)

    # ── migration ────────────────────────────────────────────────────

    def _migrate_research_out(self):
        """Move '[topic] …' rows out of facts and into research.

        Runs once; takes a backup first because this rewrites his real
        memory file and getting it wrong would lose things he told her.
        """
        facts = self.long_term.get("facts", [])
        research = [f for f in facts if _RESEARCH_RE.match(str(f))]
        if not research:
            return
        try:
            shutil.copy(self.memory_file, self.memory_file + ".before_split")
        except Exception:
            pass
        keep = [f for f in facts if not _RESEARCH_RE.match(str(f))]
        self.long_term["facts"] = keep
        seen = set(self.long_term.get("research", []))
        self.long_term["research"] = list(self.long_term.get("research", [])) + \
            [r for r in research if r not in seen]
        self.save()
        print(f"[Memory] separated {len(research)} research note(s) from "
              f"{len(keep)} personal fact(s) — backup written to "
              f"{os.path.basename(self.memory_file)}.before_split")

    # ── writing ──────────────────────────────────────────────────────

    def remember(self, fact):
        fact = str(fact).strip()
        if not fact:
            return
        bucket = "research" if _RESEARCH_RE.match(fact) else "facts"
        if fact not in self.long_term[bucket]:
            self.long_term[bucket].append(fact)
            self.save()

    def forget(self, fact):
        needle = str(fact).lower()
        for bucket in ("facts", "research"):
            self.long_term[bucket] = [
                x for x in self.long_term[bucket]
                if needle not in str(x).lower()]
        self.save()

    def set_profile(self, key, value):
        """Structured facts that deserve to be more than a sentence —
        trade, location, business, current projects."""
        self.long_term.setdefault("profile", {})[key] = value
        self.save()

    # ── reading ──────────────────────────────────────────────────────

    def get_all(self):
        """Personal facts ONLY. Research is deliberately excluded — it
        used to be 84% of what this returned, which is how it ended up
        in a system prompt instead of the things Shaun actually said."""
        return list(self.long_term.get("facts", []))

    def get_research(self):
        return list(self.long_term.get("research", []))

    def get_profile(self):
        return dict(self.long_term.get("profile", {}))

    def about_owner(self, limit=18) -> str:
        """A briefing on Shaun, for any tool that needs to write AS him
        or FOR him. This is what the website builder was missing."""
        p = self.get_profile()
        lines = []
        if p:
            for key in ("name", "location", "trade", "business",
                        "specialisms", "current_projects", "notes"):
                if p.get(key):
                    v = p[key]
                    if isinstance(v, (list, tuple)):
                        v = ", ".join(str(x) for x in v)
                    lines.append(f"{key.replace('_', ' ').title()}: {v}")
        facts = self.get_all()[:limit]
        if facts:
            lines.append("Other things he has told me:")
            lines.extend(f"- {f}" for f in facts)
        return "\n".join(lines)
