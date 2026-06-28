"""
researcher.py
─────────────
JARVIS autonomous research engine.
Location: C:\jarvis_v18\brain\researcher.py
"""

import threading
import json
import re
from datetime import datetime
from pathlib import Path

try:
    from ddgs import DDGS
    DDGS_OK = True
except Exception:
    DDGS_OK = False


KNOWLEDGE_FILE = Path(r"C:\jarvis_v18\memory\knowledge.json")
VAULT_PATH     = Path(r"C:\Users\gameboks\OneDrive\Documents\JARVIS_CORE")


class Researcher:

    def __init__(self, memory_store=None, obsidian=None,
                 on_progress=None, on_complete=None):
        self.memory      = memory_store
        self.obsidian    = obsidian
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.knowledge   = self._load_knowledge()
        self.active      = False
        count = len(self.knowledge)
        if count:
            topics = ", ".join(list(self.knowledge.keys())[:5])
            print(f"[Research] Loaded {count} topics: {topics}")
        else:
            print("[Research] No prior knowledge found.")
        print("[Research] Researcher engine ready.")

    # ── PERSISTENCE ─────────────────────────────

    def _load_knowledge(self) -> dict:
        try:
            if KNOWLEDGE_FILE.exists():
                return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_knowledge(self):
        try:
            KNOWLEDGE_FILE.parent.mkdir(exist_ok=True)
            KNOWLEDGE_FILE.write_text(
                json.dumps(self.knowledge, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Research] Save error: {e}")

    # ── PROGRESS REPORTING ──────────────────────

    def _progress(self, msg: str):
        """Send a live update to the chat window."""
        print(f"[Research] {msg}")
        if self.on_progress:
            self.on_progress(f"🔬 {msg}")

    def _complete(self, msg: str):
        """Send final completion message."""
        print(f"[Research] COMPLETE: {msg}")
        if self.on_complete:
            self.on_complete(msg)

    # ── RECALL ──────────────────────────────────

    def recall(self, topic: str) -> str:
        topic_lower = topic.lower().strip()
        for key in self.knowledge:
            if topic_lower in key.lower() or key.lower() in topic_lower:
                data    = self.knowledge[key]
                summary = data.get("summary", "")
                facts   = data.get("facts", [])
                studied = data.get("studied_at", "unknown")
                count   = data.get("fact_count", len(facts))
                result  = f"I have studied '{key}' ({studied}) — {count} facts stored.\n\n"
                if summary:
                    result += f"{summary}\n\n"
                if facts:
                    result += "Key facts:\n" + "\n".join(f"- {f}" for f in facts[:8])
                return result
        return ""

    def list_topics(self) -> str:
        if not self.knowledge:
            return "I have not studied any topics yet, sir."
        lines = []
        for k, v in self.knowledge.items():
            count   = v.get("fact_count", 0)
            studied = v.get("studied_at", "unknown")
            lines.append(f"- {k} ({count} facts, studied {studied})")
        return f"I have studied {len(self.knowledge)} topic(s):\n" + "\n".join(lines)

    # ── STUDY ASYNC ─────────────────────────────

    def study_async(self, topic: str, depth: int = 10) -> str:
        """Start research in background — returns immediately."""
        if self.active:
            return "I am already researching a topic, sir. Please wait."
        self.active = True
        t = threading.Thread(
            target=self._study_thread,
            args=(topic, depth),
            daemon=True
        )
        t.start()
        return (f"Research initiated, sir. I am now studying '{topic}'. "
                f"I will update you with progress and notify you when complete.")

    def _study_thread(self, topic: str, depth: int):
        try:
            self._study(topic, depth)
        except Exception as e:
            self._complete(f"Research failed for '{topic}': {e}")
        finally:
            self.active = False

    # ── CORE STUDY ──────────────────────────────

    def _study(self, topic: str, depth: int = 10):

        self._progress(f"Starting research on '{topic}'...")

        if not DDGS_OK:
            self._complete("Web search not available for research, sir.")
            return

        all_text  = []
        sources   = []

        # Phase 1 — Search multiple queries
        queries = [
            topic,
            f"{topic} fundamentals overview",
            f"{topic} key concepts principles",
            f"{topic} applications examples",
        ]

        total_queries = len(queries)
        for idx, query in enumerate(queries, 1):
            try:
                self._progress(f"Searching ({idx}/{total_queries}): {query}...")
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=depth // len(queries) + 2))
                for r in results:
                    body = r.get("body", "").strip()
                    if body and len(body) > 80:
                        all_text.append(body)
                        href = r.get("href", "")
                        if href and href not in sources:
                            sources.append(href)
            except Exception as e:
                print(f"[Research] Search error: {e}")

        if not all_text:
            self._complete(f"I could not find sufficient information on '{topic}', sir.")
            return

        self._progress(f"Processing {len(all_text)} sources...")

        # Phase 2 — Extract facts
        combined  = " ".join(all_text)
        sentences = re.split(r'(?<=[.!?])\s+', combined)

        topic_word = topic.lower().split()[0]
        good = []
        for s in sentences:
            s = s.strip()
            if (40 < len(s) < 300
                    and topic_word in s.lower()
                    and not s.startswith("{")
                    and not s.startswith("[")):
                good.append(s)

        # Deduplicate
        seen  = set()
        facts = []
        for s in good:
            key = s[:50].lower()
            if key not in seen:
                seen.add(key)
                facts.append(s)
            if len(facts) >= 40:
                break

        self._progress(f"Extracted {len(facts)} facts. Building knowledge summary...")

        # Phase 3 — Summary
        summary = " ".join(facts[:4])[:500].strip()

        # Phase 4 — Save
        self._progress("Saving to permanent memory and Obsidian vault...")

        self.knowledge[topic] = {
            "summary":    summary,
            "facts":      facts,
            "sources":    sources[:6],
            "studied_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fact_count": len(facts),
        }
        self._save_knowledge()

        # Save top facts to main memory
        if self.memory:
            for fact in facts[:6]:
                short = fact[:120].strip()
                if not short.endswith("."): short += "."
                self.memory.remember(f"[{topic}] {short}")

        # Save to Obsidian Knowledge folder
        if self.obsidian:
            try:
                content = (
                    f"## Summary\n\n{summary}\n\n"
                    f"## Key Facts ({len(facts)} total)\n\n"
                    + "\n".join(f"- {f}" for f in facts[:25])
                    + f"\n\n## Sources\n\n"
                    + "\n".join(f"- {s}" for s in sources[:6])
                )
                self.obsidian.save_knowledge(
                    topic, content,
                    ["research", "jarvis", "auto-study"]
                )
            except Exception as e:
                print(f"[Research] Obsidian error: {e}")

        # Final completion message
        self._complete(
            f"Research complete, sir. I have permanently stored {len(facts)} facts "
            f"about '{topic}' in my knowledge base and Obsidian vault. "
            f"You can ask me anything about it at any time."
        )