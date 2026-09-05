"""
clean_knowledge.py — one-time tidy-up.
──────────────────────────────────────
Allison's autonomous Mind used to study topics on its own and it built
up dozens of near-duplicate entries ("E-commerce optimization for
Shopify", "E-commerce store optimization strategies for Shopify", …).
This merges the near-duplicates (keeping the richest one) and empties
the leftover research queue so nothing auto-studies on the next launch.

It BACKS UP your knowledge file first, so nothing is ever lost.

Run once:   C:\\jarvis\\.venv\\Scripts\\python.exe C:\\jarvis\\clean_knowledge.py
"""

import json
import re
import shutil
from datetime import datetime
from difflib import SequenceMatcher

import config

KNOW = config.KNOWLEDGE_FILE
QUEUE = config.MEMORY_DIR / "research_queue.json"

SIM = 0.86          # how similar two topics must be to count as duplicates


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _facts(entry) -> int:
    try:
        return int(entry.get("fact_count", len(entry.get("facts", []))))
    except Exception:
        return 0


def main():
    if not KNOW.exists():
        print(f"No knowledge file at {KNOW} — nothing to clean.")
        return

    data = json.loads(KNOW.read_text(encoding="utf-8"))
    total = len(data)
    if total == 0:
        print("Knowledge base is empty — nothing to clean.")
        return

    # backup first
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = KNOW.with_name(f"knowledge.backup_{stamp}.json")
    shutil.copy2(KNOW, backup)
    print(f"Backed up your current knowledge to:\n  {backup}\n")

    keys = list(data.keys())
    norm = {k: _norm(k) for k in keys}

    used = set()
    groups = []
    for i, k in enumerate(keys):
        if k in used:
            continue
        group = [k]
        used.add(k)
        for k2 in keys[i + 1:]:
            if k2 in used:
                continue
            if SequenceMatcher(None, norm[k], norm[k2]).ratio() >= SIM:
                group.append(k2)
                used.add(k2)
        groups.append(group)

    cleaned = {}
    merged_count = 0
    for group in groups:
        # keep the entry with the most facts (richest)
        best = max(group, key=lambda k: _facts(data[k]))
        cleaned[best] = data[best]
        if len(group) > 1:
            merged_count += len(group) - 1
            print(f"• Merged {len(group)} → kept \"{best[:60]}\" "
                  f"({_facts(data[best])} facts)")
            for k in group:
                if k != best:
                    print(f"      dropped: \"{k[:60]}\"")

    KNOW.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False),
                    encoding="utf-8")

    # empty the leftover research queue so nothing auto-studies
    try:
        if QUEUE.exists():
            q = json.loads(QUEUE.read_text(encoding="utf-8"))
            had = len(q.get("queue", []))
            q["queue"] = []
            QUEUE.write_text(json.dumps(q, indent=2), encoding="utf-8")
            if had:
                print(f"\nCleared {had} leftover queued topics so they won't "
                      f"auto-study on next launch.")
    except Exception as e:
        print(f"(couldn't clear the research queue: {e})")

    print(f"\nDone. {total} topics → {len(cleaned)} "
          f"({merged_count} duplicates merged). "
          f"Backup kept at {backup.name} if you ever want it back.")


if __name__ == "__main__":
    main()
