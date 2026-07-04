import os
import re
import shutil
from datetime import datetime


class SelfUpgradeAgent:
    """
    Reads JARVIS's own source files, asks Claude for ONE small, safe,
    concrete improvement, and applies it only after explicit approval.
    Never rewrites whole files — only targeted find/replace edits.
    """

    # Only these files are eligible for self-upgrade edits.
    # Add more paths here as you trust the process.
    ALLOWED_FILES = [
        "brain/brain.py",
        "agents/system_agent.py",
        "core/controller.py",
        "hud/worker.py",
    ]

    def __init__(self, client, project_root):
        self.client = client
        self.project_root = project_root
        self.pending = None  # holds the current unapproved suggestion

    # ------------------------------------------------------------

    def _read_allowed_files(self):
        chunks = []
        for rel_path in self.ALLOWED_FILES:
            full_path = os.path.join(self.project_root, rel_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                chunks.append(f"### FILE: {rel_path}\n{content}")
        return "\n\n".join(chunks)

    # ------------------------------------------------------------

    def suggest_upgrade(self):
        code_context = self._read_allowed_files()

        prompt = (
            "You are reviewing your own source code (you are JARVIS). "
            "Suggest exactly ONE small, safe, concrete improvement. "
            "Do not suggest a rewrite of an entire file. "
            "Pick something specific: a bug, a missing error handler, "
            "a small readability or safety improvement, one new tiny "
            "capability, etc.\n\n"
            "Respond in EXACTLY this format, nothing else:\n\n"
            "FILE: <relative path from the list below>\n"
            "FIND: <exact short snippet of existing code, unique in the file>\n"
            "REPLACE: <the replacement code>\n"
            "EXPLANATION: <one or two plain sentences, said to Shaun directly>\n\n"
            f"Eligible files:\n{', '.join(self.ALLOWED_FILES)}\n\n"
            f"Current code:\n{code_context}"
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

        parsed = self._parse_suggestion(raw)
        if not parsed:
            return "I couldn't format a clean suggestion that time. Ask me again."

        self.pending = parsed
        return (
            f"Here's what I'd suggest, sir: {parsed['explanation']} "
            f"(file: {parsed['file']}). Want me to go ahead? Yes or no."
        )

    # ------------------------------------------------------------

    def _parse_suggestion(self, raw):
        try:
            file_m = re.search(r"FILE:\s*(.+)", raw)
            find_m = re.search(r"FIND:\s*(.*?)\nREPLACE:", raw, re.S)
            replace_m = re.search(r"REPLACE:\s*(.*?)\nEXPLANATION:", raw, re.S)
            expl_m = re.search(r"EXPLANATION:\s*(.+)", raw, re.S)

            file_path = file_m.group(1).strip()
            find_text = find_m.group(1).strip("\n")
            replace_text = replace_m.group(1).strip("\n")
            explanation = expl_m.group(1).strip()

            if file_path not in self.ALLOWED_FILES:
                return None

            return {
                "file": file_path,
                "find": find_text,
                "replace": replace_text,
                "explanation": explanation,
            }
        except Exception:
            return None

    # ------------------------------------------------------------

    def apply_pending(self):
        if not self.pending:
            return "There's nothing pending for me to apply, sir."

        rel_path = self.pending["file"]
        full_path = os.path.join(self.project_root, rel_path)

        if not os.path.exists(full_path):
            self.pending = None
            return f"I can't find {rel_path} anymore. Cancelling that one."

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if self.pending["find"] not in content:
            self.pending = None
            return (
                "The code I was going to change doesn't match what's "
                "actually in the file anymore. Cancelling, rather than "
                "guessing. Ask me for a fresh suggestion."
            )

        # Backup first, always.
        backup_dir = os.path.join(self.project_root, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{os.path.basename(rel_path)}.{stamp}.bak"
        shutil.copy2(full_path, os.path.join(backup_dir, backup_name))

        new_content = content.replace(
            self.pending["find"], self.pending["replace"], 1
        )

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        done = self.pending
        self.pending = None
        return (
            f"Done. I updated {done['file']} and backed up the original "
            f"as backups/{backup_name}. Restart me to load the change, sir."
        )

    # ------------------------------------------------------------

    def reject_pending(self):
        if not self.pending:
            return "Nothing was pending, sir."
        self.pending = None
        return "Understood. Cancelled — no changes made."