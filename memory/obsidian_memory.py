"""
obsidian_memory.py
──────────────────
Bridges JARVIS memory into your Obsidian JARVIS_CORE vault.

Drop this file into:  C:\jarvis_v18\memory\obsidian_memory.py

Usage in brain/brain.py:
    from memory.obsidian_memory import ObsidianBridge
    self.obsidian = ObsidianBridge()

    # When remembering something:
    self.obsidian.remember(fact)

    # When logging a conversation:
    self.obsidian.log_conversation(user_text, jarvis_reply)

    # When completing a task:
    self.obsidian.log_task(task_name, result)
"""

import os
import json
from datetime import datetime
from pathlib import Path


# ──────────────────────────────────────────────
#  CONFIGURE YOUR VAULT PATH HERE
# ──────────────────────────────────────────────
VAULT_PATH = Path(os.environ.get(
    "JARVIS_VAULT",
    r"C:\Users\{}\Documents\JARVIS_CORE".format(os.environ.get("USERNAME", "User"))
))

# Folder structure inside the vault
FOLDERS = {
    "memories":  VAULT_PATH / "Memories",
    "logs":      VAULT_PATH / "Logs",
    "tasks":     VAULT_PATH / "Tasks",
    "knowledge": VAULT_PATH / "Knowledge",
    "sessions":  VAULT_PATH / "Logs" / "Sessions",
}


class ObsidianBridge:
    """
    Writes JARVIS data into the Obsidian JARVIS_CORE vault.
    All methods fail silently so JARVIS keeps running even if
    the vault path is wrong or Obsidian is not installed.
    """

    def __init__(self, vault_path: str = None):
        if vault_path:
            self.vault = Path(vault_path)
        else:
            self.vault = VAULT_PATH

        self._ready = False
        self._init_vault()

    # ──────────────────────────────────────────
    #  SETUP
    # ──────────────────────────────────────────

    def _init_vault(self):
        """Create all required folders if they don't exist."""
        try:
            for name, path in FOLDERS.items():
                full = self.vault / path.relative_to(VAULT_PATH)
                full.mkdir(parents=True, exist_ok=True)

            self._ensure_home()
            self._ready = True
            print(f"[Obsidian] Vault connected: {self.vault}")
        except Exception as e:
            print(f"[Obsidian] Vault not found or not accessible: {e}")
            print(f"[Obsidian] Tried path: {self.vault}")
            print("[Obsidian] JARVIS will continue without Obsidian sync.")

    def _ensure_home(self):
        """Create the System/Home.md dashboard if it doesn't exist."""
        system_dir = self.vault / "System"
        system_dir.mkdir(exist_ok=True)
        home = system_dir / "Home.md"
        if not home.exists():
            home.write_text(
                "# JARVIS CORE\n\n"
                "## Systems\n\n"
                "- Brain: Online\n"
                "- Voice: Online\n"
                "- Memory: Online\n"
                "- HUD: Online\n\n"
                "## Quick Links\n\n"
                "- [[Memories/Index]]\n"
                "- [[Tasks/Index]]\n"
                "- [[Knowledge/Index]]\n"
                "- [[Logs/Index]]\n\n"
                "## Recent\n\n"
                "```dataview\n"
                "TABLE file.mtime AS Modified\n"
                "FROM \"Memories\"\n"
                "SORT file.mtime DESC\n"
                "LIMIT 10\n"
                "```\n",
                encoding="utf-8"
            )

    # ──────────────────────────────────────────
    #  MEMORIES
    # ──────────────────────────────────────────

    def remember(self, fact: str) -> bool:
        """
        Save a memory as a markdown note in Memories/.
        File is named by date so memories group naturally.
        """
        if not self._ready:
            return False
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            mem_file = self.vault / "Memories" / f"{today}.md"

            now_str = datetime.now().strftime("%H:%M")

            if mem_file.exists():
                # Append to today's memory file
                existing = mem_file.read_text(encoding="utf-8")
                mem_file.write_text(
                    existing + f"- {now_str} — {fact}\n",
                    encoding="utf-8"
                )
            else:
                # Create today's memory file
                mem_file.write_text(
                    f"# Memories — {today}\n\n"
                    f"Tags: #memory #jarvis\n\n"
                    f"---\n\n"
                    f"- {now_str} — {fact}\n",
                    encoding="utf-8"
                )

            self._update_memory_index()
            print(f"[Obsidian] Memory saved: {fact[:50]}")
            return True

        except Exception as e:
            print(f"[Obsidian] Memory save error: {e}")
            return False

    def _update_memory_index(self):
        """Keep an index of all memory files."""
        try:
            mem_dir = self.vault / "Memories"
            files = sorted(mem_dir.glob("*.md"), reverse=True)
            index = mem_dir / "Index.md"

            lines = ["# Memory Index\n\n", "Tags: #index\n\n", "---\n\n"]
            for f in files:
                if f.name != "Index.md":
                    date = f.stem
                    lines.append(f"- [[{date}]]\n")

            index.write_text("".join(lines), encoding="utf-8")
        except Exception:
            pass

    # ──────────────────────────────────────────
    #  CONVERSATION LOGS
    # ──────────────────────────────────────────

    def log_conversation(self, user_text: str, jarvis_reply: str) -> bool:
        """
        Append every conversation exchange to today's session log.
        Lives in Logs/Sessions/YYYY-MM-DD.md
        """
        if not self._ready:
            return False
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            now_str = datetime.now().strftime("%H:%M:%S")
            log_dir = self.vault / "Logs" / "Sessions"
            log_file = log_dir / f"{today}.md"

            entry = (
                f"\n### {now_str}\n\n"
                f"**Shaun:** {user_text}\n\n"
                f"**JARVIS:** {jarvis_reply}\n\n"
                f"---\n"
            )

            if log_file.exists():
                existing = log_file.read_text(encoding="utf-8")
                log_file.write_text(existing + entry, encoding="utf-8")
            else:
                log_file.write_text(
                    f"# Session Log — {today}\n\n"
                    f"Tags: #log #session #jarvis\n\n"
                    f"---\n"
                    + entry,
                    encoding="utf-8"
                )
            return True

        except Exception as e:
            print(f"[Obsidian] Log error: {e}")
            return False

    # ──────────────────────────────────────────
    #  TASKS
    # ──────────────────────────────────────────

    def add_task(self, task: str, priority: str = "normal") -> bool:
        """Add a task to Tasks/Active.md"""
        if not self._ready:
            return False
        try:
            task_file = self.vault / "Tasks" / "Active.md"
            today = datetime.now().strftime("%Y-%m-%d")
            now_str = datetime.now().strftime("%H:%M")

            entry = f"- [ ] {task} *(added {today} {now_str})* #{priority}\n"

            if task_file.exists():
                existing = task_file.read_text(encoding="utf-8")
                task_file.write_text(existing + entry, encoding="utf-8")
            else:
                task_file.write_text(
                    "# Active Tasks\n\n"
                    "Tags: #tasks #active\n\n"
                    "---\n\n"
                    + entry,
                    encoding="utf-8"
                )
            print(f"[Obsidian] Task added: {task[:50]}")
            return True

        except Exception as e:
            print(f"[Obsidian] Task error: {e}")
            return False

    def complete_task(self, task: str) -> bool:
        """Mark a task as complete and move it to Tasks/Completed.md"""
        if not self._ready:
            return False
        try:
            active_file = self.vault / "Tasks" / "Active.md"
            done_file   = self.vault / "Tasks" / "Completed.md"

            if not active_file.exists():
                return False

            lines = active_file.read_text(encoding="utf-8").splitlines(keepends=True)
            remaining = []
            completed = []

            for line in lines:
                if task.lower() in line.lower() and "- [ ]" in line:
                    completed.append(
                        line.replace("- [ ]", "- [x]")
                    )
                else:
                    remaining.append(line)

            active_file.write_text("".join(remaining), encoding="utf-8")

            if completed:
                today = datetime.now().strftime("%Y-%m-%d %H:%M")
                done_entry = f"\n*(Completed {today})*\n" + "".join(completed)
                if done_file.exists():
                    done_file.write_text(
                        done_file.read_text(encoding="utf-8") + done_entry,
                        encoding="utf-8"
                    )
                else:
                    done_file.write_text(
                        "# Completed Tasks\n\nTags: #tasks #done\n\n---\n"
                        + done_entry,
                        encoding="utf-8"
                    )
            return True

        except Exception as e:
            print(f"[Obsidian] Complete task error: {e}")
            return False

    # ──────────────────────────────────────────
    #  KNOWLEDGE
    # ──────────────────────────────────────────

    def save_knowledge(self, title: str, content: str, tags: list = None) -> bool:
        """
        Save a piece of knowledge as a note in Knowledge/.
        Great for things JARVIS researches or learns.
        """
        if not self._ready:
            return False
        try:
            safe_title = "".join(
                c for c in title if c.isalnum() or c in " _-"
            ).strip()
            know_file = self.vault / "Knowledge" / f"{safe_title}.md"
            tag_str = " ".join(f"#{t}" for t in (tags or ["knowledge", "jarvis"]))
            today = datetime.now().strftime("%Y-%m-%d")

            know_file.write_text(
                f"# {title}\n\n"
                f"Tags: {tag_str}\n"
                f"Created: {today}\n\n"
                f"---\n\n"
                f"{content}\n",
                encoding="utf-8"
            )
            print(f"[Obsidian] Knowledge saved: {title}")
            return True

        except Exception as e:
            print(f"[Obsidian] Knowledge error: {e}")
            return False

    # ──────────────────────────────────────────
    #  STATUS
    # ──────────────────────────────────────────

    def status(self) -> dict:
        """Return vault status — used by the HUD diagnostics panel."""
        if not self._ready:
            return {"connected": False, "vault": str(self.vault)}

        try:
            mem_count  = len(list((self.vault / "Memories").glob("*.md")))
            task_count = 0
            task_file  = self.vault / "Tasks" / "Active.md"
            if task_file.exists():
                content = task_file.read_text(encoding="utf-8")
                task_count = content.count("- [ ]")

            return {
                "connected":    True,
                "vault":        str(self.vault),
                "memory_files": mem_count,
                "active_tasks": task_count,
            }
        except Exception:
            return {"connected": False, "vault": str(self.vault)}