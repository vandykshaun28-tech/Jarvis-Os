"""
tool_result.py — the execution contract.

THE RULE THIS FILE EXISTS TO ENFORCE:
    A tool either produced a real result, or it failed. There is no
    third state, and neither state is expressed in prose.

Before this file, a tool returned a string like "Sending failed, sir: 500"
and the harness decided whether that counted as success by searching the
first 120 characters for the word "error". Lowercase "failed" was not in
the list, so a failed send was written into Allison's activity ledger as
status="ok". She then read her own ledger, saw a success, and told Shaun
the email went out. She was not lying — she was misinformed by her own
bookkeeping.

A ToolResult makes that impossible. `ok` is a boolean set by the code that
actually did the work (or caught the exception). Nothing downstream is
allowed to infer success from wording.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """The only thing a tool is allowed to return."""

    tool: str
    ok: bool
    summary: str = ""            # one line, for the model and the ledger
    data: dict = field(default_factory=dict)   # structured payload
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error: str = ""              # populated iff ok is False
    http_status: int | None = None
    duration_ms: int | None = None

    # confirmation gate — a destructive tool returns ok=False plus this,
    # meaning "nothing has happened yet, ask the human first"
    needs_confirmation: bool = False
    confirm_token: str = ""
    confirm_prompt: str = ""

    # ── constructors ──────────────────────────────────────────────

    @classmethod
    def success(cls, tool, summary, **kw):
        return cls(tool=tool, ok=True, summary=summary, **kw)

    @classmethod
    def failure(cls, tool, error, **kw):
        return cls(tool=tool, ok=False, error=str(error),
                   summary=f"FAILED: {str(error)[:160]}", **kw)

    @classmethod
    def from_exception(cls, tool, exc, **kw):
        return cls(tool=tool, ok=False, error=f"{type(exc).__name__}: {exc}",
                   summary=f"FAILED: {type(exc).__name__}: {str(exc)[:140]}",
                   stderr=traceback.format_exc()[-1200:], **kw)

    @classmethod
    def confirm(cls, tool, prompt, token, data=None):
        """Nothing was done. The human must approve first."""
        return cls(tool=tool, ok=False, needs_confirmation=True,
                   confirm_token=token, confirm_prompt=prompt,
                   data=data or {},
                   summary=f"AWAITING CONFIRMATION: {prompt[:140]}")

    # ── what the model is allowed to see ──────────────────────────

    def to_model(self, limit=3000) -> str:
        """Rendered tool result fed back as the tool_result block.

        Deliberately blunt. The model gets an explicit verdict line it
        cannot misread, so it never has to infer outcome from tone.
        """
        if self.needs_confirmation:
            head = (f"[{self.tool}] NOT EXECUTED — CONFIRMATION REQUIRED.\n"
                    f"Nothing has been changed yet. Ask Shaun this exact "
                    f"question and wait for a yes:\n  {self.confirm_prompt}\n"
                    f"If he agrees, call this tool again with "
                    f"confirm=\"{self.confirm_token}\".")
            return head

        verdict = "SUCCEEDED" if self.ok else "FAILED"
        lines = [f"[{self.tool}] {verdict}."]
        if self.summary:
            lines.append(self.summary)
        if self.http_status is not None:
            lines.append(f"HTTP status: {self.http_status}")
        if self.exit_code is not None:
            lines.append(f"exit code: {self.exit_code}")
        if self.stdout.strip():
            lines.append(f"--- stdout ---\n{self.stdout.strip()[:limit]}")
        if self.stderr.strip() and not self.ok:
            lines.append(f"--- stderr ---\n{self.stderr.strip()[:800]}")
        if self.data:
            try:
                blob = json.dumps(self.data, indent=2, default=str)
            except Exception:
                blob = str(self.data)
            lines.append(f"--- data ---\n{blob[:limit]}")
        if self.error:
            lines.append(f"--- error ---\n{self.error[:800]}")
        if not self.ok:
            lines.append("You MUST tell Shaun this did not work. Do not "
                         "describe it as done.")
        return "\n".join(lines)

    def __str__(self):
        return self.to_model()


# Migration-only. Legacy tools return prose, so for THOSE we still have
# to guess — but we guess over the whole string with a list that includes
# the lowercase and contraction forms the original 6-word check missed
# ("failed", "couldn't", "refused", "paused", "ran out"), which is what
# let real failures be logged as successes.
_FAILURE_MARKERS = (
    "failed", "failure", "error", "could not", "couldn't", "cannot",
    "can't", "unable", "offline", "unavailable", "refused", "denied",
    "paused", "ran out", "timed out", "timeout", "not found", "missing",
    "no such", "invalid", "unauthorised", "unauthorized", "forbidden",
    "aborted", "cancelled", "canceled", "rejected", "crashed", "traceback",
)


def coerce(tool_name, value) -> ToolResult:
    """Wrap a legacy tool that still returns a bare string.

    A real ToolResult passes straight through with its asserted verdict.
    A bare string has no verdict to assert, so we infer one — and record
    `verdict_inferred` so these stragglers stay findable rather than
    blending in with tools that actually report their own status.
    """
    if isinstance(value, ToolResult):
        return value
    text = "" if value is None else str(value)
    low = text.lower()
    looks_failed = any(m in low for m in _FAILURE_MARKERS)
    return ToolResult(
        tool=tool_name,
        ok=not looks_failed,
        summary=text[:300],
        stdout=text,
        error=text[:300] if looks_failed else "",
        data={"verdict_inferred": True})


def unmigrated(results) -> list:
    """Which tools in this batch never asserted their own status."""
    return sorted({r.tool for r in results
                   if r.data.get("verdict_inferred")})


class Stopwatch:
    """Times a tool call so duration lands in the result, not a guess."""

    def __enter__(self):
        self._t = time.time()
        return self

    def __exit__(self, *a):
        self.ms = int((time.time() - self._t) * 1000)
        return False

    @property
    def elapsed_ms(self):
        return getattr(self, "ms", int((time.time() - self._t) * 1000))
