"""
verify_toolcore.py — proves the rebuilt tool core actually behaves.

Run:  python verify_toolcore.py

This does NOT test that tools succeed. It tests the far more important
property: that when a tool does NOT run, or runs and FAILS, Allison
cannot report success. Every check below is a scenario that used to
produce a confident lie.

PySide6 is stubbed so the real brain logic can be exercised headlessly.
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── stub PySide6 so brain.py imports without a GUI ─────────────────
if "PySide6" not in sys.modules:
    q = types.ModuleType("PySide6")
    qc = types.ModuleType("PySide6.QtCore")

    class _Sig:
        def __init__(self, *a, **k): pass
        def __get__(self, o, t=None): return self
        def connect(self, *a, **k): pass
        def emit(self, *a, **k): pass

    class _QObject:
        def __init__(self, *a, **k): pass

    class _QTimer(_QObject):
        def start(self, *a, **k): pass
        def stop(self, *a, **k): pass
        timeout = _Sig()

    qc.QObject, qc.Signal, qc.QTimer = _QObject, _Sig, _QTimer
    qc.Qt = types.SimpleNamespace()
    qc.QThread = _QObject
    q.QtCore = qc
    sys.modules["PySide6"] = q
    sys.modules["PySide6.QtCore"] = qc

import json                                         # noqa: E402
from tool_result import ToolResult, coerce          # noqa: E402
import tool_gate as gate                        # noqa: E402
from brain import llm as llm_mod                           # noqa: E402

def _real_tool_defs():
    """Pull the real tool schema list out of brain.py without building a
    Brain (which needs a GUI, audio and a live LLM client)."""
    import re as _re
    src = Path("brain/brain.py").read_text(encoding="utf-8")
    names = _re.findall(r'\{"name": "(\w+)",\s*\n\s*"description"', src)
    return [{"name": n, "description": "", "input_schema": {}}
            for n in dict.fromkeys(names)]


PASS, FAIL = [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}")
    if detail:
        print(f"         {detail}")


print("=" * 66)
print("ALLISON TOOL-CORE VERIFICATION")
print("=" * 66)

# ── 0. the brain must actually IMPORT ──────────────────────────────
# This check exists because its absence shipped a crash to Shaun.
# Every other check in this file exercised the modules AROUND brain.py —
# tool_result, tool_gate, llm, the two tools — and brain.py itself was
# only ever read as TEXT to scrape tool names. So a circular import that
# made the whole app fail to start passed 44/44 without a murmur.
# A test suite that never imports the file it is testing is theatre.
print("\n0. THE BRAIN LOADS — import brain.brain for real")

try:
    import importlib
    import brain.brain as _bb
    importlib.reload(_bb) if "brain.brain" in sys.modules else None
    check("brain.brain imports without error", True)
    check("JarvisBrain class is present", hasattr(_bb, "JarvisBrain"))
    check("ToolResult wired into brain", hasattr(_bb, "ToolResult"))
    check("coerce wired into brain", callable(getattr(_bb, "_coerce", None)))
    check("tool gate wired into brain",
          callable(getattr(_bb, "_gate_tools", None)))
except Exception as _e:
    check("brain.brain imports without error", False,
          f"{type(_e).__name__}: {_e}")
    check("JarvisBrain class is present", False, "(brain did not import)")
    check("ToolResult wired into brain", False, "(brain did not import)")
    check("coerce wired into brain", False, "(brain did not import)")
    check("tool gate wired into brain", False, "(brain did not import)")

# and load it the way the RUNNING APP actually does — core/worker.py
# uses spec_from_file_location, not a package import, so a package-import
# test alone would not have caught this class of failure either.
try:
    import importlib.util as _ilu, os as _os
    _bp = _os.path.abspath("brain/brain.py")
    _sp = _ilu.spec_from_file_location("JarvisBrainModule", _bp)
    _m = _ilu.module_from_spec(_sp)
    _sp.loader.exec_module(_m)
    check("brain.py loads the way core/worker.py loads it",
          hasattr(_m, "JarvisBrain"))
except Exception as _e:
    check("brain.py loads the way core/worker.py loads it", False,
          f"{type(_e).__name__}: {_e}")

# every module the running app touches must import cleanly too
for _mod in ("brain.llm", "tool_result", "tool_gate",
             "tools.shopify_tool", "tools.website_tool",
             "core.phone_server"):
    try:
        __import__(_mod)
        check(f"{_mod} imports", True)
    except Exception as _e:
        check(f"{_mod} imports", False, f"{type(_e).__name__}: {_e}")


# The exact condition that killed website_build on Shaun's PC:
# `brain` bound in sys.modules as a plain MODULE with no __path__, so
# every `from brain.x import ...` dies with "'brain' is not a package".
# The shared contract now lives at top level for this reason; this check
# makes sure it stays there.
try:
    import types as _t, os as _o
    _saved = sys.modules.get("brain")
    _fake = _t.ModuleType("brain")
    _fake.__file__ = _o.path.abspath("brain/brain.py")   # NO __path__
    sys.modules["brain"] = _fake
    for _m in ("tool_result", "tool_gate"):
        sys.modules.pop(_m, None)
    import importlib as _il
    _tr2 = _il.import_module("tool_result")
    _wt2 = _il.import_module("tools.website_tool")
    check("tools still import when 'brain' is not a package",
          hasattr(_tr2, "ToolResult") and hasattr(_wt2, "website_build"))
except Exception as _e:
    check("tools still import when 'brain' is not a package", False,
          f"{type(_e).__name__}: {_e}")
finally:
    if _saved is not None:
        sys.modules["brain"] = _saved
    else:
        sys.modules.pop("brain", None)


# ── 1. verdicts come from the result, not the wording ──────────────
print("\n1. VERDICT INTEGRITY — wording must not decide success")

r = ToolResult.failure("send_email", "SMTP refused: 535 auth failed")
check("explicit failure stays failed", r.ok is False)
check("model sees the word FAILED", "FAILED" in r.to_model())
check("model is told not to claim success",
      "do not describe it as done" in r.to_model().lower())

# the exact strings that used to be logged as SUCCESS
for phrase in ["Sending failed, sir: 500",
               "I couldn't finish that on screen, sir.",
               "PAUSED FOR YOU, SIR: needs your card",
               "I ran out of my 25-step budget",
               "REFUSED — this looks like a sensitive field"]:
    c = coerce("legacy_tool", phrase)
    check(f"legacy failure detected: {phrase[:38]!r}", c.ok is False)

ok_phrase = coerce("legacy_tool", "Opened Chrome, sir.")
check("legacy success still reads as success", ok_phrase.ok is True)

# ── 1b. a tool call typed as TEXT gets RUN, not shown ──────────────
# Seen live 2026-08-08: an 8B model could not manage the structured
# format for a 14-parameter tool, so it typed the call out as prose and
# Shaun got a wall of JSON where his website should have been.
print("\n1b. TEXT-EMITTED TOOL CALLS — recovered, not displayed")

import re as _re2
_PAT = _re2.compile(
    r'[<(]\s*function(?:_call)?\s*[=:]\s*[\"\']?([A-Za-z_][A-Za-z0-9_]*)'
    r'[\"\']?\s*>?\s*(\{.*?\})\s*(?:<\s*/\s*function(?:_call)?\s*>|$)',
    _re2.S)

_leak = ('(function=website_build>{"name": "mezzanine_floors", '
         '"title": "Mezzanine Floors"}</function>')
_m = _PAT.search(_leak)
check("the exact leak from his screen is parsed",
      bool(_m) and _m.group(1) == "website_build")
check("its arguments survive as real JSON",
      bool(_m) and json.loads(_m.group(2))["name"] == "mezzanine_floors")
check("proper <function=…> form parses too",
      bool(_PAT.search('<function=draw_image>{"prompt":"x"}</function>')))
check("ordinary prose is NOT mistaken for a call",
      _PAT.search("I used the function to work out boost pressure.") is None)

_src = Path("brain/brain.py").read_text(encoding="utf-8")
check("brain wires the salvage into the reply path",
      "_salvage_text_tool_call" in _src and "recovered from a mis-formatted" in _src)
check("salvage is recorded in the ledger, not hidden",
      "salvaged_tool_call" in _src)
check("weak brains get a slimmed schema, not 14 params",
      "_ESSENTIAL_ARGS" in _src)


# ── 1c. failure diagnosis must not blame the wrong provider ────────
# Seen live: Gemini returned 429 (quota) and Anthropic returned 400 (no
# credit). The old handler searched the COMBINED string for "gemini"
# and "400" together, concluded the Gemini key was invalid, and sent
# Shaun off to regenerate a key that was working perfectly.
print("\n1c. BRAIN-FAILURE DIAGNOSIS — per provider, not across them")

try:
    import importlib.util as _iu, os as _os2
    _sp2 = _iu.spec_from_file_location("_BM", _os2.path.abspath("brain/brain.py"))
    _bm = _iu.module_from_spec(_sp2)
    _sp2.loader.exec_module(_bm)
    _B = _bm.JarvisBrain
    _err = ('groq: HTTP 429 (rate limit): try again in 7.5s | '
            'gemini: HTTP 429: {"error":{"code":429,"message":"You exceeded '
            'your current quota","details":[{"retryDelay":"32s"}]}} | '
            'anthropic: Error code: 400 - Your credit balance is too low')
    _out = _B._diagnose_brain_failure(_B, _err)
    check("does NOT claim the Gemini key is invalid",
          "key looks invalid" not in _out and "REJECTED" not in _out)
    check("names groq's real problem", "rate limited" in _out)
    check("names gemini's real problem", "quota" in _out.lower())
    check("names anthropic's real problem", "out of credit" in _out)
    check("reports a real retry delay from the provider",
          "~8 second" in _out or "~8s" in _out or "about 8 second" in _out,
          _out.splitlines()[-3] if len(_out.splitlines()) > 3 else "")
    check("retryDelay is parsed from Gemini's JSON",
          _B._retry_seconds('{"retryDelay":"32s"}') == 33)
    check("no delay invented when none is given",
          _B._retry_seconds("something went wrong") is None)
except Exception as _e:
    for _n in ("does NOT claim the Gemini key is invalid",
               "names groq's real problem", "names gemini's real problem",
               "names anthropic's real problem",
               "reports a real retry delay from the provider",
               "retryDelay is parsed from Gemini's JSON",
               "no delay invented when none is given"):
        check(_n, False, f"{type(_e).__name__}: {_e}")


# ── 2. confirmation gate ───────────────────────────────────────────
print("\n2. CONFIRMATION GATE — destructive work must not auto-run")

c = ToolResult.confirm("shopify_update_price",
                       "Change price from 100 to 1 on the LIVE store?",
                       "abc123")
check("confirm result is not ok", c.ok is False)
check("confirm result flags itself", c.needs_confirmation is True)
m = c.to_model()
check("model told nothing happened", "NOT EXECUTED" in m)
check("model given the token to re-call with", "abc123" in m)

# ── 3. tool gating ─────────────────────────────────────────────────
print("\n3. CONTEXT GATING — only relevant tools per turn")

defs = [{"name": n, "description": "", "input_schema": {}} for n in
        ["shopify_orders", "shopify_products", "website_build",
         "code_project", "draw_image", "paper_trade", "browser_goto",
         "open_app", "web_search", "remember_fact", "list_tasks",
         "read_file", "write_file", "take_screenshot", "vision_search"]]

shop = {t["name"] for t in gate.gate(defs, "how many orders today?")}
check("shopify turn exposes shopify_orders", "shopify_orders" in shop)
check("shopify turn hides paper_trade", "paper_trade" not in shop,
      f"exposed: {sorted(shop)}")

site = {t["name"] for t in gate.gate(defs, "build me a website for the shop")}
check("website turn exposes website_build", "website_build" in site)

check("gating actually reduces the list", len(shop) < len(defs),
      f"{len(defs)} tools → {len(shop)} for a shopify turn")

# and against the REAL catalogue, which is what actually ships
real_defs = _real_tool_defs()
if real_defs:
    r_shop = gate.gate(real_defs, "how many orders did i get this week?")
    r_site = gate.gate(real_defs, "build me a landing page")
    r_chat = gate.gate(real_defs, "what do you think of this idea")
    check("real catalogue: shopify turn is narrowed",
          len(r_shop) < len(real_defs),
          f"{len(real_defs)} → {len(r_shop)}")
    check("real catalogue: website turn is narrowed",
          len(r_site) < len(real_defs),
          f"{len(real_defs)} → {len(r_site)}")
    check("real catalogue: plain chat still gets a usable set",
          5 <= len(r_chat) < len(real_defs),
          f"{len(real_defs)} → {len(r_chat)}")
    # Fail-open fires only when the gate matches NOTHING at all — e.g. a
    # catalogue whose tools have all been renamed. Empty text is not that
    # case: it routes to GENERAL, which is the designed behaviour.
    unknown = [{"name": f"renamed_tool_{i}", "description": "",
                "input_schema": {}} for i in range(9)]
    check("unrecognisable catalogue falls back open (never mute)",
          len(gate.gate(unknown, "do the thing")) == len(unknown))
    check("empty text still routes to the GENERAL set",
          0 < len(gate.gate(real_defs, "")) < len(real_defs),
          f"{len(real_defs)} → {len(gate.gate(real_defs, ''))}")

# ── 4. provider routing ────────────────────────────────────────────
print("\n4. PROVIDER ROUTING — tools never go to a brain that fakes them")

provs = llm_mod._providers()
check("groq is tool-capable", provs["groq"]["tools"] is True)
check("gemini is tool-capable", provs["gemini"]["tools"] is True)
check("anthropic is tool-capable", provs["anthropic"]["tools"] is True)
check("openrouter marked NOT tool-capable", provs["openrouter"]["tools"] is False)
check("ollama marked NOT tool-capable", provs["ollama"]["tools"] is False)

src = Path("brain/llm.py").read_text(encoding="utf-8")
check("silent tool-disarm is gone",
      "oa_tools = None\n                        continue" not in src
      and "if glitches >= 2:\n                            oa_tools = None" not in src)
check("glitch now fails over instead of narrating",
      "could not produce a valid tool call" in src)

# a tool-bearing turn with NO tool-capable provider configured must
# refuse outright rather than answering from a text-only brain
import config                                              # noqa: E402
saved_order = config.LLM_PROVIDER_ORDER
try:
    config.LLM_PROVIDER_ORDER = ["openrouter", "ollama"]
    engine = llm_mod.UniversalLLM()
    out = engine.run_tool_loop(
        system="s", history=[], user_content="delete everything",
        tools=[{"name": "x", "description": "", "input_schema": {}}],
        execute=lambda n, a: "should never run")
    check("tool turn refused when no tool-capable brain",
          out["provider"] is None and out["tools_available"] is False,
          f"error: {out['error'][:90]}")
finally:
    config.LLM_PROVIDER_ORDER = saved_order

# ── 5. the website tool tells the truth ────────────────────────────
print("\n5. REAL EXECUTION — website tool, verified on disk")

import tempfile                                            # noqa: E402
from tools import website_tool as wt                       # noqa: E402

saved_root = wt.PROJECTS_ROOT
try:
    wt.PROJECTS_ROOT = Path(tempfile.mkdtemp()).resolve()
    b = wt.website_build(name="verify-site", title="Verify",
                         sections=[{"heading": "a", "body": "b"}])
    check("build reports ok", b.ok is True, b.summary)
    idx = Path(b.data["open_with"])
    check("index.html genuinely exists on disk", idx.exists())
    check("reported byte count matches the real file",
          idx.stat().st_size == b.data["files"]["index.html"]["bytes"],
          f"disk={idx.stat().st_size} reported="
          f"{b.data['files']['index.html']['bytes']}")

    import hashlib                                         # noqa: E402
    real = hashlib.sha256(idx.read_bytes()).hexdigest()
    check("reported sha256 matches the real file",
          real == b.data["files"]["index.html"]["sha256"])

    again = wt.website_build(name="verify-site", title="Verify")
    check("second build asks before overwriting",
          again.needs_confirmation and not again.ok)
finally:
    wt.PROJECTS_ROOT = saved_root

# ── 6. shopify tool fails honestly without credentials ─────────────
print("\n6. REAL EXECUTION — shopify tool with no credentials")

import os                                                  # noqa: E402
from tools import shopify_tool as st                       # noqa: E402

saved_env = {k: os.environ.pop(k, None)
             for k in ("SHOPIFY_STORE", "SHOPIFY_TOKEN")}
saved_cfg = (getattr(config, "SHOPIFY_STORE", ""),
             getattr(config, "SHOPIFY_TOKEN", ""))
try:
    config.SHOPIFY_STORE = ""
    config.SHOPIFY_TOKEN = ""
    o = st.shopify_orders(days=7)
    check("unconfigured shopify returns FAILED", o.ok is False)
    check("it says what is missing", "SHOPIFY_STORE" in o.error)
    check("it states no store was contacted",
          "NOT contacted" in o.error or "not contacted" in o.error.lower())
finally:
    config.SHOPIFY_STORE, config.SHOPIFY_TOKEN = saved_cfg
    for k, v in saved_env.items():
        if v is not None:
            os.environ[k] = v

# ── 7. the phone path is untouched ─────────────────────────────────
print("\n7. PHONE / TAILSCALE PATH — must still work from the iPhone")

ps = Path("core/phone_server.py").read_text(encoding="utf-8")
check("/api/chat still present", '"/api/chat"' in ps)
check("/api/see still present", '"/api/see"' in ps)
check("phone still calls brain.process", "brain.process(text" in ps)
check("phone still calls brain.identify_image",
      "brain.identify_image(" in ps)
check("auth still enforced", "_authed()" in ps)
check("server still binds all interfaces for Tailscale",
      'host="0.0.0.0"' in ps)
# the shared-session architecture: both windows, one transcript
check("phone tags its turns as coming from the phone",
      'source="phone"' in ps)
check("phone can read the shared transcript", '"/api/events"' in ps)
check("phone composer grows with the text",
      "composer.scrollHeight" in ps)
try:
    from core.session import SharedSession
    import tempfile as _tf, os as _os
    _s = SharedSession(_os.path.join(_tf.mkdtemp(), "s.json"))
    _got = []
    _s.subscribe(lambda m: _got.append(m))
    _s.append("user", "from the desk", source="pc")
    _s.append("user", "from the phone", source="phone")
    _first = _s.since(0)
    _after = _s.since(_first["cursor"])
    check("shared session: both devices land in one transcript",
          len(_first["messages"]) == 2
          and {m["source"] for m in _first["messages"]} == {"pc", "phone"})
    check("shared session: listeners fire live (no refresh)", len(_got) == 2)
    check("shared session: cursor returns only what is new",
          _after["messages"] == [])
except Exception as _e:
    check("shared session: both devices land in one transcript", False,
          f"{type(_e).__name__}: {_e}")
    check("shared session: listeners fire live (no refresh)", False, "")
    check("shared session: cursor returns only what is new", False, "")

# ── result ─────────────────────────────────────────────────────────
print("\n" + "=" * 66)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED CHECKS:")
    for f in FAIL:
        print(f"  • {f}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
