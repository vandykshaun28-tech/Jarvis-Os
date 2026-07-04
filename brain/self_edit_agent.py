"""
self_edit_agent.py
───────────────────────────────────────────────────────────────────────────
Lets JARVIS propose changes to his own source code, but NEVER applies them
without explicit human approval. Flow:

  1. You ask Jarvis to add/change something specific and scoped
     (e.g. "add a method to pc_control to open VS Code").
  2. Jarvis reads the target file, asks Claude to write ONLY that change,
     and writes the full proposed file to <name>.pending_edit.py
     (the real file is never touched at this point).
  3. The pending file is opened in VS Code (via pc_control) so you can
     read the diff yourself.
  4. You say "approve edit" or "reject edit". Only on approval does the
     agent: git commit the current state as a safety checkpoint, replace
     the real file with the pending one, and tell you to restart Jarvis.

Git is used purely as a rollback net — every approved edit is preceded by
a commit of the pre-edit state, so `git revert` always gets you back.
"""

import os
import subprocess
import difflib
from pathlib import Path
from datetime import datetime


class SelfEditAgent:
    def __init__(self, anthropic_client, repo_root, on_status=None, model="claude-sonnet-4-6"):
        """
        anthropic_client : an already-constructed Anthropic() client (reuse brain.client)
        repo_root        : path to the git repo root containing jarvis's own source
        on_status         : optional callback(str) for HUD/chat/voice updates
        """
        self.client     = anthropic_client
        self.repo_root  = Path(repo_root)
        self.on_status  = on_status or (lambda msg: None)
        self.model      = model
        self.pending    = None   # {"target": Path, "pending_path": Path, "summary": str}

    # ── internal helpers ─────────────────────────────────────────────
    def _say(self, msg):
        print(f"[SelfEdit] {msg}")
        self.on_status(msg)

    def _git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo_root), *args],
            capture_output=True, text=True
        )

    def _ensure_clean_git(self):
        """Refuse to start an edit if there are already uncommitted changes —
        keeps the rollback checkpoint meaningful."""
        status = self._git("status", "--porcelain")
        return status.stdout.strip() == ""

    # ── step 1: propose ──────────────────────────────────────────────
    def propose_edit(self, relative_path: str, instruction: str) -> str:
        """
        relative_path : path to the file, relative to repo_root
                         (e.g. "jarvis_v18/pc_control.py")
        instruction   : a SCOPED description of the change. The narrower
                         the better — this is not "improve yourself",
                         this is "add a method that does X".
        """
        target = self.repo_root / relative_path
        if not target.exists():
            return f"I can't find {relative_path} in the repo, sir."

        if self.pending is not None:
            return (f"There is already a pending edit to "
                    f"{self.pending['target'].name} awaiting your approval, sir. "
                    f"Approve or reject it first.")

        if not self._ensure_clean_git():
            return ("There are uncommitted changes in the repo already, sir. "
                    "Please commit or stash them before I propose an edit — "
                    "I need a clean checkpoint to roll back to.")

        original_code = target.read_text(encoding="utf-8")

        system = (
            "You are JARVIS's self-modification subroutine. You will be given "
            "the full current contents of one of your own Python source files "
            "and a specific, scoped instruction for a change. "
            "Output ONLY the complete, updated file contents — no markdown "
            "fences, no commentary, no explanation. The file must remain "
            "syntactically valid Python and must not remove unrelated "
            "functionality. Keep the change minimal and exactly scoped to "
            "the instruction given."
        )
        user_msg = (
            f"FILE: {relative_path}\n\n"
            f"INSTRUCTION: {instruction}\n\n"
            f"CURRENT CONTENTS:\n{original_code}"
        )

        self._say(f"Drafting proposed change to {target.name}...")

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            new_code = "".join(
                b.text for b in response.content if hasattr(b, "text")
            ).strip()
        except Exception as e:
            return f"Drafting failed, sir: {e}"

        # strip accidental code fences just in case
        if new_code.startswith("```"):
            new_code = new_code.split("\n", 1)[1]
            if new_code.rstrip().endswith("```"):
                new_code = new_code.rstrip()[:-3]

        # quick sanity check: must parse as Python before we even show it
        try:
            compile(new_code, str(target), "exec")
        except SyntaxError as e:
            return f"The proposed change has a syntax error, sir — discarding it. ({e})"

        pending_path = target.with_suffix(target.suffix + ".pending_edit.py")
        pending_path.write_text(new_code, encoding="utf-8")

        diff = list(difflib.unified_diff(
            original_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile=f"{target.name} (current)",
            tofile=f"{target.name} (proposed)",
        ))
        diff_summary = "".join(diff[:80])  # cap for sanity

        self.pending = {
            "target": target,
            "pending_path": pending_path,
            "instruction": instruction,
            "timestamp": datetime.now().isoformat(),
        }

        diff_path = target.with_suffix(target.suffix + ".pending_edit.diff")
        diff_path.write_text("".join(diff), encoding="utf-8")

        self._say(
            f"Proposed edit to {target.name} ready for your review, sir. "
            f"{len(diff) - 4 if len(diff) > 4 else 0} lines changed. "
            f"Diff saved to {diff_path.name}. Say 'approve edit' or 'reject edit'."
        )
        return diff_summary or "No diff produced — proposed file may be identical."

    # ── step 2a: approve ─────────────────────────────────────────────
    def approve_edit(self) -> str:
        if self.pending is None:
            return "There is no pending edit to approve, sir."

        target       = self.pending["target"]
        pending_path = self.pending["pending_path"]

        # checkpoint commit of current (pre-edit) state
        self._git("add", "-A")
        commit = self._git(
            "commit", "-m",
            f"checkpoint before self-edit: {target.name} "
            f"({self.pending['instruction'][:60]})"
        )

        new_code = pending_path.read_text(encoding="utf-8")
        target.write_text(new_code, encoding="utf-8")

        self._git("add", "-A")
        self._git("commit", "-m", f"self-edit approved: {target.name}")

        pending_path.unlink(missing_ok=True)
        diff_path = target.with_suffix(target.suffix + ".pending_edit.diff")
        diff_path.unlink(missing_ok=True)

        applied = target.name
        self.pending = None
        self._say(
            f"Edit to {applied} approved and committed, sir. "
            f"A restart is required for the change to take effect."
        )
        return f"Applied and committed. Restart me to load the new {applied}."

    # ── step 2b: reject ──────────────────────────────────────────────
    def reject_edit(self) -> str:
        if self.pending is None:
            return "There is no pending edit to reject, sir."
        target = self.pending["target"]
        self.pending["pending_path"].unlink(missing_ok=True)
        diff_path = target.with_suffix(target.suffix + ".pending_edit.diff")
        diff_path.unlink(missing_ok=True)
        name = target.name
        self.pending = None
        self._say(f"Discarded the proposed edit to {name}, sir.")
        return f"Edit to {name} discarded. Nothing was changed."

    def status(self) -> str:
        if self.pending is None:
            return "No pending self-edit, sir."
        p = self.pending
        return (f"Pending edit to {p['target'].name} — \"{p['instruction']}\" "
                f"— proposed at {p['timestamp']}. Awaiting approval.")