"""
researcher.py
─────────────
Allison's research engine — studies a topic ONLY when Shaun asks
(the autonomous Mind no longer queues research on its own).
Location: C:/jarvis/brain/researcher.py
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


import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import config

KNOWLEDGE_FILE = config.KNOWLEDGE_FILE
VAULT_PATH     = config.VAULT_PATH


class Researcher:

    def __init__(self, memory_store=None, obsidian=None,
                 on_progress=None, on_complete=None,
                 on_percent=None, llm=None):
        self.memory      = memory_store
        self.obsidian    = obsidian
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_percent  = on_percent      # (topic, percent:int, stage:str)
        self.llm         = llm             # LLM adapter for real synthesis
        self.knowledge   = self._load_knowledge()
        self.active      = False
        self._topic      = ""
        self.percent     = 0               # live 0-100 for the UI to read
        self.stage       = ""
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

    def _pct(self, percent: int, stage: str):
        """Publish a live percentage so the UI can draw a progress bar."""
        self.percent = max(0, min(100, int(percent)))
        self.stage = stage
        print(f"[Research] {self.percent}% — {stage}")
        if self.on_percent:
            try:
                self.on_percent(self._topic, self.percent, stage)
            except Exception as e:
                print(f"[Research] percent callback error: {e}")

    def _complete(self, msg: str):
        """Send final completion message."""
        print(f"[Research] COMPLETE: {msg}")
        if self.on_complete:
            self.on_complete(msg)

    # ── RECALL ──────────────────────────────────

    def recall(self, topic: str) -> str:
        topic_lower = topic.lower().strip()
        match_key = None
        # 1) direct substring either way
        for key in self.knowledge:
            kl = key.lower()
            if topic_lower in kl or kl in topic_lower:
                match_key = key
                break
        # 2) keyword overlap (handles "study gambling addiction" vs "gambling")
        if match_key is None:
            qwords = set(self._keywords(topic_lower))
            best, best_score = None, 0
            for key in self.knowledge:
                kwords = set(self._keywords(key.lower()))
                score = len(qwords & kwords)
                if score > best_score:
                    best, best_score = key, score
            if best_score:
                match_key = best
        # 3) fuzzy (handles misspellings like "gambleing" -> "gambling")
        if match_key is None:
            import difflib
            near = difflib.get_close_matches(
                topic_lower, [k.lower() for k in self.knowledge], n=1, cutoff=0.7)
            if near:
                for key in self.knowledge:
                    if key.lower() == near[0]:
                        match_key = key
                        break
        if match_key is not None:
            for key in (match_key,):
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
        self._topic = topic
        self._pct(2, f"starting research on {topic}")
        t = threading.Thread(
            target=self._study_thread,
            args=(topic, depth),
            daemon=True
        )
        t.start()
        return (f"On it, sir — I'm studying '{topic}' now. Watch the progress "
                f"bar on screen (and on the AI Agents page); I'll tell you the "
                f"moment it hits 100%.")

    def _study_thread(self, topic: str, depth: int):
        try:
            self._study(topic, depth)
        except Exception as e:
            self._pct(100, f"failed: {e}")
            self._complete(f"Research failed for '{topic}': {e}")
        finally:
            self.active = False

    # ── CORE STUDY ──────────────────────────────

    @staticmethod
    def _keywords(topic: str):
        """Meaningful search words from a topic, punctuation stripped."""
        stop = {"the","a","an","and","or","to","of","for","in","on","how",
                "what","why","is","are","i","you","me","my","your","vs",
                "with","from","best","make","want","know","begin","start",
                "some","real","how-to"}
        words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]+", topic.lower())
        return [w for w in words if w not in stop] or words

    def _study(self, topic: str, depth: int = 10):

        self._topic = topic
        self._progress(f"Starting research on '{topic}'...")
        self._pct(5, f"planning research on {topic}")

        all_text  = []
        sources   = []
        used_web  = False

        # Phase 1 — Search the web (best-effort). If ddgs is missing or
        # every query fails, we DON'T give up — we fall back to the LLM's
        # own knowledge below, so a study never silently does nothing.
        if DDGS_OK:
            keywords = self._keywords(topic)
            core     = " ".join(keywords[:5]) or topic
            queries = [
                core,
                f"{core} guide fundamentals",
                f"{core} key concepts tips",
                f"{core} examples how it works",
            ]
            total = len(queries)
            for idx, query in enumerate(queries, 1):
                # searching spans 5% → 45%
                self._pct(5 + int(40 * (idx - 1) / total),
                          f"searching the web ({idx}/{total})")
                self._progress(f"Searching ({idx}/{total}): {query}...")
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(
                            query, max_results=depth // total + 2))
                    for r in results:
                        body = r.get("body", "").strip()
                        if body and len(body) > 80:
                            all_text.append(body)
                            href = r.get("href", "")
                            if href and href not in sources:
                                sources.append(href)
                except Exception as e:
                    print(f"[Research] Search error: {e}")
            used_web = bool(all_text)
        else:
            self._progress("Web search module offline — studying from my own "
                           "knowledge instead.")

        self._pct(50, "reading and understanding the material")

        # Phase 2 — SYNTHESISE with the LLM (this is the real learning).
        # Works on any brain (Groq/Gemini/etc.) — pure text, no vision,
        # no credits required. Falls back gracefully if no LLM is wired.
        facts = []
        summary = ""
        synthesised = False
        if self.llm is not None:
            src_blob = ""
            if all_text:
                src_blob = "\n\n".join(all_text)[:6000]
            try:
                self._pct(62, "writing a clear summary")
                sysp = ("You are Allison, a sharp researcher. Study the topic "
                        "and produce accurate, genuinely useful knowledge. If "
                        "web notes are provided, ground your answer in them; "
                        "otherwise use your own reliable knowledge and say so. "
                        "Be concrete and correct.")
                if src_blob:
                    up = (f"Topic: {topic}\n\nWeb notes gathered:\n{src_blob}\n\n"
                          f"Write a clear 5-6 sentence SUMMARY of {topic} for "
                          f"someone learning it.")
                else:
                    up = (f"Topic: {topic}\n\nWrite a clear 5-6 sentence "
                          f"SUMMARY of {topic} for someone learning it, from "
                          f"your own knowledge.")
                summary = (self.llm.simple(sysp, up, max_tokens=400) or "").strip()

                self._pct(78, "extracting the key facts")
                up2 = (f"Topic: {topic}\n\n"
                       + (f"Web notes:\n{src_blob}\n\n" if src_blob else "")
                       + "List 12 of the most important, specific FACTS about "
                       "this topic. One per line, start each line with '- '. "
                       "No preamble, just the facts.")
                raw = self.llm.simple(sysp, up2, max_tokens=700) or ""
                for line in raw.splitlines():
                    line = line.strip().lstrip("-•*0123456789. ").strip()
                    if len(line) > 15:
                        facts.append(line)
                synthesised = bool(summary or facts)
            except Exception as e:
                print(f"[Research] LLM synthesis error: {e}")

        # Phase 2b — if no LLM (or it failed) fall back to sentence
        # extraction from the web notes so we still store SOMETHING real.
        if not synthesised and all_text:
            combined  = " ".join(all_text)
            sentences = re.split(r'(?<=[.!?])\s+', combined)
            kw = set(self._keywords(topic)[:8])
            good = [s.strip() for s in sentences
                    if 40 < len(s.strip()) < 300
                    and any(w in s.lower() for w in kw)
                    and not s.strip().startswith(("{", "["))]
            if not good:
                good = sorted((x.strip() for x in sentences
                               if 60 < len(x.strip()) < 300),
                              key=len, reverse=True)[:25]
            seen = set()
            for s in good:
                k = s[:50].lower()
                if k not in seen:
                    seen.add(k); facts.append(s)
                if len(facts) >= 30:
                    break
            summary = summary or " ".join(facts[:4])[:500].strip()

        # Absolute last resort — never claim success with nothing.
        if not facts and not summary:
            self._pct(100, "no material found")
            self._complete(
                f"I'm sorry, sir — I couldn't gather anything solid on "
                f"'{topic}'. My web search came back empty and I have no brain "
                f"available to study from. Type 'test brains' to see what's "
                f"live, then ask me to study it again.")
            return

        # Phase 4 — Save
        self._pct(90, "saving to permanent memory")
        self._progress("Saving to permanent memory and Obsidian vault...")

        self.knowledge[topic] = {
            "summary":    summary,
            "facts":      facts,
            "sources":    sources[:6],
            "studied_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fact_count": len(facts),
            "via":        "web+brain" if used_web else "brain",
        }
        self._save_knowledge()

        if self.memory:
            for fact in facts[:6]:
                short = fact[:120].strip()
                if not short.endswith("."): short += "."
                self.memory.remember(f"[{topic}] {short}")

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
                    topic, content, ["research", "allison", "auto-study"])
            except Exception as e:
                print(f"[Research] Obsidian error: {e}")

        self._pct(100, "done")
        how = "the web and my own knowledge" if used_web else "my own knowledge"
        self._complete(
            f"Done, sir — I've studied '{topic}' using {how} and permanently "
            f"stored {len(facts)} facts. Ask me anything about it: say "
            f"\"what do you know about {topic}\".")