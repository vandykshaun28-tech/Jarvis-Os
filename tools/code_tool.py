"""
code_tool.py — write code, RUN it, read the real error, fix it.

What makes a coding assistant useful is not writing plausible code. It
is the loop: write, execute, look at what actually came back, and change
the code based on that. Without the run step a model is guessing, and a
confident guess that was never executed is exactly the failure this
whole rebuild has been about.

So this tool:
  1. plans the files,
  2. writes them and verifies every byte on disk,
  3. RUNS the entry point and captures real stdout, stderr and exit code,
  4. if it failed, hands the REAL traceback back to the model and tries
     again, up to a fixed number of attempts,
  5. reports what actually happened, including "still broken after N
     attempts" when that is the truth.

Execution safety: everything runs inside the projects folder with a
timeout, and the first run of a project needs confirmation. Generated
code executing unattended on Shaun's own machine is not something to
opt him into silently.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from tool_result import ToolResult, Stopwatch

PROJECTS_ROOT = Path(getattr(config, "PROJECTS_DIR",
                             Path(config.ROOT_DIR) / "projects")).resolve()

RUN_TIMEOUT = 60
MAX_FIX_ATTEMPTS = 3
MAX_FILE_BYTES = 400_000


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip()).strip("-.")
    return (slug or "project")[:64].lower()


def _token_for(action: str, detail: str) -> str:
    raw = f"{action}|{detail}|{int(time.time() // 600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _inside_root(p: Path) -> bool:
    try:
        p.resolve().relative_to(PROJECTS_ROOT)
        return True
    except ValueError:
        return False


def _write_verify(path: Path, text: str) -> dict:
    data = text.encode("utf-8")
    want = hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if not path.exists():
        return {"ok": False, "error": "file missing after write"}
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"ok": got == want, "bytes": path.stat().st_size,
            "sha256": got,
            "error": "" if got == want else "hash mismatch after write"}


def _extract_json(raw):
    t = str(raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"```\s*$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    depth, start = 0, -1
    for i, ch in enumerate(t):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(t[start:i + 1])
                except Exception:
                    start = -1
    return None


def _run(entry: Path, cwd: Path) -> dict:
    """Execute and capture what REALLY happened."""
    if entry.suffix == ".py":
        cmd = [sys.executable, entry.name]
    elif entry.suffix in (".js", ".mjs"):
        cmd = ["node", entry.name]
    else:
        return {"ran": False, "reason": f"don't know how to run {entry.name}"}
    with Stopwatch() as sw:
        try:
            p = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                               text=True, timeout=RUN_TIMEOUT)
            return {"ran": True, "exit_code": p.returncode,
                    "stdout": (p.stdout or "")[-4000:],
                    "stderr": (p.stderr or "")[-4000:],
                    "ms": sw.elapsed_ms, "cmd": " ".join(cmd)}
        except subprocess.TimeoutExpired:
            return {"ran": True, "exit_code": -1, "stdout": "",
                    "stderr": f"timed out after {RUN_TIMEOUT}s — probably "
                              f"waiting for input or looping forever",
                    "ms": sw.elapsed_ms, "cmd": " ".join(cmd)}
        except FileNotFoundError as e:
            return {"ran": False, "reason": f"{cmd[0]} is not installed: {e}"}
        except Exception as e:
            return {"ran": False, "reason": f"{type(e).__name__}: {e}"}


_PLAN_SYS = (
    "You are a senior engineer. Plan a small, COMPLETE, runnable project. "
    "Reply with ONLY a JSON object, no prose, no code fence:\n"
    '{"summary": "one line", "entry": "main.py", '
    '"files": [{"path": "main.py", "content": "..."}]}\n'
    "RULES:\n"
    "- Every file's content must be complete and runnable. No '...', no "
    "'TODO', no placeholder bodies.\n"
    "- The entry file must run to completion on its own and PRINT "
    "something that proves it worked. It must not wait for input.\n"
    "- Standard library only unless the brief says otherwise — a missing "
    "pip package means it cannot run here.\n"
    "- Relative paths only, no leading slash, no '..'.")


def code_write(name: str,
               brief: str = "",
               about: str = "",
               run: bool = True,
               confirm: str = "",
               think=None,
               progress=None) -> ToolResult:
    """Write a real project, run it, and fix it from the real error."""
    tool = "code_write"
    if think is None:
        return ToolResult.failure(
            tool, "no model available to write the code with")

    slug = _safe_slug(name or brief)
    folder = (PROJECTS_ROOT / slug).resolve()
    if not _inside_root(folder):
        return ToolResult.failure(tool, f"refused: {folder} is outside "
                                        f"{PROJECTS_ROOT}")

    def say(m):
        if progress:
            try:
                progress(m)
            except Exception:
                pass

    # running generated code is opt-in, per project
    if run:
        want = _token_for("run", slug)
        if confirm != want:
            return ToolResult.confirm(
                tool,
                f"I'll write this project to {folder} and then RUN it to "
                f"check it works ({RUN_TIMEOUT}s limit, inside that folder "
                f"only). Writing is safe; running executes code I just "
                f"generated on your PC. Go ahead?",
                want, data={"folder": str(folder), "will_run": True})

    # ── 1. plan ──────────────────────────────────────────────────────
    say("① Designing the project…")
    who = f"\n\nContext about the owner:\n{about}" if about else ""
    try:
        plan = _extract_json(think(_PLAN_SYS, f"Build: {brief or name}{who}"))
    except Exception as e:
        return ToolResult.from_exception(tool, e)
    if not isinstance(plan, dict) or not plan.get("files"):
        return ToolResult.failure(
            tool, "the model did not return a usable project plan")

    files = [f for f in plan["files"]
             if isinstance(f, dict) and f.get("path")][:20]
    if not files:
        return ToolResult.failure(tool, "plan contained no files")
    entry_name = str(plan.get("entry") or files[0]["path"])

    # ── 2. write + verify ────────────────────────────────────────────
    say(f"② Writing {len(files)} file(s)…")
    existing = [f["path"] for f in files if (folder / f["path"]).exists()]
    evidence, written = {}, []
    for f in files:
        rel = str(f["path"]).strip().lstrip("/\\")
        if not rel or ".." in rel:
            continue
        dest = (folder / rel).resolve()
        if not _inside_root(dest):
            continue
        content = str(f.get("content", ""))
        if len(content.encode()) > MAX_FILE_BYTES:
            return ToolResult.failure(tool, f"{rel} is too large to write")
        ev = _write_verify(dest, content)
        evidence[rel] = ev
        if ev["ok"]:
            written.append(rel)
    bad = {k: v for k, v in evidence.items() if not v["ok"]}
    if bad:
        return ToolResult.failure(
            tool, "wrote files but verification failed: "
                  + ", ".join(f"{k} ({v.get('error')})" for k, v in bad.items()),
            data={"evidence": evidence})

    entry = (folder / entry_name).resolve()
    if not entry.exists():
        entry = (folder / written[0]).resolve() if written else None

    result_base = {
        "folder": str(folder), "files": written, "entry": str(entry or ""),
        "overwrote": existing,
        "bytes": sum(v["bytes"] for v in evidence.values()),
        "summary": str(plan.get("summary", ""))[:300],
    }

    if not run or entry is None:
        say(f"③ Done — {len(written)} file(s) written and verified.")
        return ToolResult.success(
            tool, f"wrote and verified {len(written)} file(s) in {folder} "
                  f"(not run)",
            stdout="\n".join(f"  {p}  {evidence[p]['bytes']} bytes"
                             for p in written),
            data=result_base)

    # ── 3. run, and fix from the REAL error ──────────────────────────
    attempts = []
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        say(f"③ Running it{'' if attempt == 1 else f' (attempt {attempt})'}…")
        r = _run(entry, folder)
        attempts.append(r)

        if not r.get("ran"):
            return ToolResult.failure(
                tool, f"wrote {len(written)} file(s) but could not run "
                      f"{entry.name}: {r.get('reason')}",
                data={**result_base, "attempts": attempts})

        if r.get("exit_code") == 0:
            say(f"④ It works — exit code 0 after {attempt} attempt(s).")
            return ToolResult.success(
                tool,
                f"{len(written)} file(s) written, verified, and RUN "
                f"successfully (exit 0"
                + (f" after {attempt} attempts" if attempt > 1 else "")
                + f"). {result_base['summary']}",
                exit_code=0, stdout=r.get("stdout", ""),
                duration_ms=r.get("ms"),
                data={**result_base, "attempts": attempts,
                      "verified_by_running": True})

        # it failed — give the model the real error, not a summary of it
        if attempt == MAX_FIX_ATTEMPTS:
            break
        say(f"   it failed (exit {r.get('exit_code')}) — reading the error "
            f"and fixing…")
        fix_sys = (
            "You are debugging code you just wrote. It FAILED when run. "
            "Below is the real traceback from the real execution. Fix the "
            "cause. Reply with ONLY a JSON object:\n"
            '{"files": [{"path": "...", "content": "full new content"}]}\n'
            "Return every file you are changing, complete. No partial "
            "files, no '...'.")
        current = "\n\n".join(
            f"--- {p} ---\n{(folder / p).read_text(encoding='utf-8')[:3000]}"
            for p in written)
        try:
            fix = _extract_json(think(
                fix_sys,
                f"Command: {r.get('cmd')}\nExit code: {r.get('exit_code')}\n"
                f"STDERR:\n{r.get('stderr', '')[:2500]}\n"
                f"STDOUT:\n{r.get('stdout', '')[:800]}\n\n"
                f"Current files:\n{current}"))
        except Exception:
            break
        if not isinstance(fix, dict) or not fix.get("files"):
            break
        for f in fix["files"]:
            rel = str(f.get("path", "")).strip().lstrip("/\\")
            if not rel or ".." in rel:
                continue
            dest = (folder / rel).resolve()
            if not _inside_root(dest):
                continue
            ev = _write_verify(dest, str(f.get("content", "")))
            evidence[rel] = ev
            if rel not in written and ev["ok"]:
                written.append(rel)

    last = attempts[-1] if attempts else {}
    say(f"④ Still failing after {len(attempts)} attempt(s) — reporting it "
        f"rather than pretending.")
    return ToolResult.failure(
        tool,
        f"Wrote {len(written)} file(s) to {folder}, but the code STILL "
        f"FAILS after {len(attempts)} attempt(s) — exit code "
        f"{last.get('exit_code')}. The files are on disk for you to look "
        f"at; do not treat this as working.",
        exit_code=last.get("exit_code"),
        stdout=last.get("stdout", ""), stderr=last.get("stderr", ""),
        data={**result_base, "attempts": attempts,
              "verified_by_running": False})


def code_run(name: str, entry: str = "", confirm: str = "") -> ToolResult:
    """Run an existing project and report what really happened."""
    tool = "code_run"
    folder = (PROJECTS_ROOT / _safe_slug(name)).resolve()
    if not _inside_root(folder) or not folder.exists():
        return ToolResult.failure(tool, f"no such project: {folder}")
    target = (folder / entry).resolve() if entry else None
    if target is None or not target.exists():
        cands = sorted(folder.glob("*.py")) + sorted(folder.glob("*.js"))
        if not cands:
            return ToolResult.failure(tool, f"nothing runnable in {folder}")
        target = cands[0]
    want = _token_for("run", folder.name)
    if confirm != want:
        return ToolResult.confirm(
            tool, f"Run {target.name} from {folder}? It executes on your PC "
                  f"with a {RUN_TIMEOUT}s limit.", want)
    r = _run(target, folder)
    if not r.get("ran"):
        return ToolResult.failure(tool, str(r.get("reason")))
    ok = r.get("exit_code") == 0
    return ToolResult(
        tool=tool, ok=ok,
        summary=(f"{target.name} exited {r.get('exit_code')}"
                 + (" — clean" if ok else " — FAILED")),
        exit_code=r.get("exit_code"), stdout=r.get("stdout", ""),
        stderr=r.get("stderr", ""), duration_ms=r.get("ms"),
        error="" if ok else f"exit code {r.get('exit_code')}",
        data={"folder": str(folder), "entry": str(target)})
