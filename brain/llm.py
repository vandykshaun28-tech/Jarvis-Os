"""
llm.py
──────
JARVIS's universal brain adapter. One interface, several providers:

  anthropic  Claude (smartest, paid credits)         [vision ✓]
  groq       Llama 3.3 70B — FREE API key            [vision ✗]
  gemini     Google Gemini Flash — FREE tier          [vision ✓]
  ollama     any local model, free forever            [vision ✗]

Groq / Gemini / Ollama all speak the OpenAI chat-completions protocol,
so one adapter covers them. When a provider dies mid-conversation
(out of credits, bad key, server down) the next one in
config.LLM_PROVIDER_ORDER takes over automatically — JARVIS never goes
brain-dead just because one tank is empty.
"""

import base64
import json
import os
import re

import httpx

import config


class ProviderDead(Exception):
    """This provider can't serve us (credits/auth/unreachable) — try next."""


class ToolCallGlitch(Exception):
    """The model fumbled a tool-call generation (Groq 'failed_generation').
    NOT a dead provider — retry, then fall back to a tool-less answer."""


def gemini_available_models(timeout=15):
    """Ask Google which models this KEY can actually use.

    Hardcoding a model name is how Allison ended up dead in the water:
    "models/gemini-2.5-flash is no longer available to new users".
    Google retires names on their own schedule, and a name that worked
    when the code was written says nothing about today. So ask.

    Returns (models, error) where models is a list of usable ids for
    generateContent, newest-looking first.
    """
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return [], "GEMINI_API_KEY not set"
    try:
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key, "pageSize": 200}, timeout=timeout)
    except Exception as e:
        return [], f"unreachable: {e}"
    if r.status_code >= 400:
        return [], f"HTTP {r.status_code}: {r.text[:180]}"
    try:
        data = r.json()
    except Exception as e:
        return [], f"non-JSON reply: {e}"
    out = []
    for m in data.get("models", []):
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        name = str(m.get("name", "")).replace("models/", "")
        if not name:
            continue
        out.append(name)

    def rank(n):
        # prefer stable aliases, then newer families, then flash over pro
        # (free tier is far kinder to flash)
        score = 0
        if n.endswith("-latest"):
            score -= 40
        mm = re.search(r"gemini-(\d+)", n)
        if mm:
            score -= int(mm.group(1)) * 10
        if "flash" in n:
            score -= 5
        if "lite" in n:
            score -= 2
        for bad in ("vision", "embedding", "aqa", "tts", "image", "live",
                    "thinking", "exp", "preview"):
            if bad in n:
                score += 25
        return (score, n)

    out.sort(key=rank)
    return out, ""


def pick_gemini_model():
    """A model id this key can really use, or the configured default."""
    models, err = gemini_available_models()
    if models:
        return models[0], models, err
    return config.GEMINI_MODEL, [], err


_GEMINI_LIVE = {"model": None, "checked": False}


def _live_gemini_model():
    """The configured model if it still exists, otherwise a real one.

    Checked once per process. A stale hardcoded name is a silent
    outage: every request 404s with "no longer available to new users"
    and the whole assistant falls through to the next brain for no
    reason a user could ever guess at.
    """
    if _GEMINI_LIVE["checked"]:
        return _GEMINI_LIVE["model"] or config.GEMINI_MODEL
    _GEMINI_LIVE["checked"] = True
    if not os.environ.get("GEMINI_API_KEY"):
        _GEMINI_LIVE["model"] = config.GEMINI_MODEL
        return config.GEMINI_MODEL
    try:
        models, err = gemini_available_models()
    except Exception:
        models, err = [], "probe failed"
    if not models:
        _GEMINI_LIVE["model"] = config.GEMINI_MODEL
        return config.GEMINI_MODEL
    want = config.GEMINI_MODEL
    if want in models:
        _GEMINI_LIVE["model"] = want
    else:
        _GEMINI_LIVE["model"] = models[0]
        print(f"[LLM] configured Gemini model {want!r} is not available to "
              f"this key — using {models[0]!r} instead. "
              f"({len(models)} usable models found)")
    return _GEMINI_LIVE["model"]


def _providers():
    """Provider table, built fresh so env-var changes are picked up.

    "tools" is a HARD capability claim, not a hope. It means: this
    provider returns real structured tool-call fields that we parse, and
    if it doesn't, that's a bug we want to see rather than absorb.

    OpenRouter's free Llama endpoints and most Ollama builds ACCEPT the
    `tools` parameter and then ignore it — replying in prose as though
    they'd used it. That is indistinguishable from success at the HTTP
    layer and is precisely how a "tool call" becomes a hallucination. So
    they are marked tools=False and are never handed a tool-bearing turn.
    """
    return {
        "anthropic": {"kind": "anthropic", "vision": True, "tools": True,
                      "model": config.CLAUDE_MODEL,
                      "ok": bool(os.environ.get("ANTHROPIC_API_KEY"))},
        "groq":      {"kind": "openai", "vision": False, "tools": True,
                      "base": "https://api.groq.com/openai/v1",
                      "model": config.GROQ_MODEL,
                      "models": [config.GROQ_MODEL]
                                + list(getattr(config, "GROQ_MODEL_FALLBACKS", [])),
                      "key": os.environ.get("GROQ_API_KEY", ""),
                      "ok": bool(os.environ.get("GROQ_API_KEY"))},
        "openrouter": {"kind": "openai", "vision": False, "tools": False,
                       "base": "https://openrouter.ai/api/v1",
                       "model": getattr(config, "OPENROUTER_MODEL",
                                        "meta-llama/llama-3.3-70b-instruct:free"),
                       "models": [getattr(config, "OPENROUTER_MODEL",
                                          "meta-llama/llama-3.3-70b-instruct:free")]
                                 + list(getattr(config,
                                        "OPENROUTER_MODEL_FALLBACKS", [])),
                       "key": os.environ.get("OPENROUTER_API_KEY", ""),
                       "ok": bool(os.environ.get("OPENROUTER_API_KEY"))},
        "gemini":    {"kind": "gemini-native", "vision": True, "tools": True,
                      "base": "https://generativelanguage.googleapis.com/v1beta",
                      # a name that Google confirms this key can use,
                      # resolved once and cached — see _live_gemini_model
                      "model": _live_gemini_model(),
                      "key": os.environ.get("GEMINI_API_KEY", ""),
                      "ok": bool(os.environ.get("GEMINI_API_KEY"))},
        "ollama":    {"kind": "openai", "vision": False, "tools": False,
                      "base": config.OLLAMA_URL,
                      "model": config.OLLAMA_MODEL,
                      "key": "ollama", "ok": True},   # probed on use
    }


# ── content conversion helpers ──────────────────

def _blocks_to_openai(content):
    """Anthropic-style content (str or block list) → OpenAI content."""
    if isinstance(content, str):
        return content
    out = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            out.append({"type": "text", "text": b["text"]})
        elif b.get("type") == "image":
            src = b.get("source", {})
            out.append({"type": "image_url", "image_url": {
                "url": f"data:{src.get('media_type','image/jpeg')};"
                       f"base64,{src.get('data','')}"}})
    return out or ""


def _blocks_to_gemini(content):
    """Anthropic-style content (str or block list) → Gemini parts."""
    if isinstance(content, str):
        return [{"text": content}]
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            parts.append({"text": b["text"]})
        elif b.get("type") == "image":
            src = b.get("source", {})
            parts.append({"inline_data": {
                "mime_type": src.get("media_type", "image/jpeg"),
                "data": src.get("data", "")}})
    return parts or [{"text": ""}]


def _tools_to_openai(tools):
    return [{"type": "function", "function": {
        "name": t["name"], "description": t.get("description", ""),
        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
    }} for t in tools]


# ── Gemini native tool-calling: JSON-Schema → Gemini function schema ──
_GTYPE = {"string": "STRING", "number": "NUMBER", "integer": "INTEGER",
          "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT"}


def _clean_gemini_schema(s):
    """Convert a JSON-Schema property into the OpenAPI subset Gemini's
    functionDeclarations accept (UPPERCASE types, recursive)."""
    if not isinstance(s, dict):
        return {"type": "STRING"}
    t = s.get("type", "string")
    if isinstance(t, list):
        t = t[0] if t else "string"
    out = {"type": _GTYPE.get(str(t).lower(), "STRING")}
    if s.get("description"):
        out["description"] = str(s["description"])[:256]
    if s.get("enum"):
        out["enum"] = [str(x) for x in s["enum"]]
    if out["type"] == "OBJECT":
        props = s.get("properties") or {}
        out["properties"] = {k: _clean_gemini_schema(v) for k, v in props.items()}
        if s.get("required"):
            out["required"] = list(s["required"])
    if out["type"] == "ARRAY":
        out["items"] = _clean_gemini_schema(s.get("items") or {"type": "string"})
    return out


def _tools_to_gemini(tools):
    """Anthropic-style tool defs → Gemini functionDeclarations. No-arg
    tools omit 'parameters' (Gemini rejects an empty OBJECT schema)."""
    decls = []
    for t in tools:
        decl = {"name": t["name"],
                "description": (t.get("description", "") or "")[:1024]}
        schema = _clean_gemini_schema(t.get("input_schema") or {})
        if schema.get("properties"):
            decl["parameters"] = schema
        decls.append(decl)
    return [{"function_declarations": decls}]


def _render_tool_output(out, limit=3000):
    """Render a tool's return value into the text the model sees.

    ToolResult renders with an explicit SUCCEEDED/FAILED verdict line so
    the model never has to infer the outcome from wording. A legacy bare
    string is passed through unchanged (see tool_result.coerce).
    """
    to_model = getattr(out, "to_model", None)
    if callable(to_model):
        return to_model(limit)
    return str(out)[:limit]


class UniversalLLM:

    def __init__(self, anthropic_client=None, cost_tracker=None):
        self.anthropic = anthropic_client
        self.active_provider = None   # last provider that worked
        self.cost_tracker = cost_tracker

    # ── low-level single calls ──────────────────

    def _anthropic_call(self, system, messages, tools, max_tokens,
                        smart=False):
        model = config.CLAUDE_MODEL if smart else getattr(
            config, "CLAUDE_MODEL_FAST", config.CLAUDE_MODEL)
        try:
            kwargs = dict(model=model, max_tokens=max_tokens,
                          system=system, messages=messages)
            if tools:
                kwargs["tools"] = tools
            resp = self.anthropic.messages.create(**kwargs)
            if self.cost_tracker is not None:
                try:
                    u = resp.usage
                    self.cost_tracker.record(model, u.input_tokens,
                                             u.output_tokens)
                except Exception as e:
                    print(f"[LLM] cost tracking failed: {e}")
            return resp
        except Exception as e:
            s = str(e).lower()
            if any(w in s for w in ("credit balance", "authentication",
                                    "401", "403", "invalid x-api-key",
                                    "overloaded", "429", "connection")):
                raise ProviderDead(str(e))
            raise

    def _openai_call(self, prov, oa_messages, oa_tools, max_tokens):
        import time
        payload = {"model": prov["model"], "messages": oa_messages,
                   "max_tokens": max_tokens}
        if oa_tools:
            payload["tools"] = oa_tools
            payload["tool_choice"] = "auto"
        url = f"{prov['base']}/chat/completions"
        if "googleapis" in prov["base"]:
            # Google's 2026-era keys authenticate via the key= URL
            # parameter (their console says so verbatim). A Bearer
            # header with these keys triggers "Invalid Auth key".
            headers = {"x-goog-api-key": prov["key"]}
            url += f"?key={prov['key']}"
        else:
            headers = {"Authorization": f"Bearer {prov['key']}"}
        for attempt in (1, 2, 3):
            try:
                r = httpx.post(url, json=payload, timeout=90, headers=headers)
            except Exception as e:
                raise ProviderDead(f"unreachable: {e}")
            # rate limits & server hiccups are TEMPORARY — wait and retry
            # instead of declaring the whole provider dead mid-conversation
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < 3:
                    time.sleep(3 * attempt)
                    continue
                raise ProviderDead(f"HTTP {r.status_code} after retries "
                                   f"(rate limit / server): {r.text[:120]}")
            if r.status_code in (401, 402, 403, 404):
                raise ProviderDead(f"HTTP {r.status_code}: {r.text[:150]}")
            try:
                data = r.json()
            except Exception as e:
                raise ProviderDead(f"non-JSON response: {e} — {r.text[:120]}")
            # Google sometimes wraps error payloads in a list
            if isinstance(data, list):
                data = data[0] if data and isinstance(data[0], dict) else {}
            if not isinstance(data, dict):
                raise ProviderDead(f"unexpected response shape: {r.text[:150]}")
            if "error" in data:
                err = data["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                if ("failed_generation" in str(data) or
                        "Failed to call a function" in msg or
                        "tool_use_failed" in str(err)):
                    raise ToolCallGlitch(msg[:160])
                raise ProviderDead(f"API error: {msg[:160]}")
            try:
                return data["choices"][0]
            except Exception as e:
                raise ProviderDead(f"bad response: {e} — {r.text[:120]}")

    def _gemini_generate(self, prov, system, contents, gtools, max_tokens):
        """Low-level Gemini generateContent that returns the candidate's
        PARTS list (so callers can see functionCall parts, not just text).
        Model-hops on 'not found', raises ProviderDead on hard failure."""
        import time
        models = [prov["model"]] + [
            m for m in getattr(config, "GEMINI_MODEL_FALLBACKS", [])
            if m != prov["model"]]
        last = None
        for model in models:
            url = (f"{prov['base']}/models/{model}:generateContent")
            payload = {"contents": contents,
                       "generationConfig": {"maxOutputTokens": max_tokens}}
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            if gtools:
                payload["tools"] = gtools
            r = None
            for attempt in (1, 2, 3):
                try:
                    r = httpx.post(url, json=payload, timeout=90,
                                   headers={"x-goog-api-key": prov["key"]})
                except Exception as e:
                    raise ProviderDead(f"unreachable: {e}")
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 3:
                        time.sleep(3 * attempt)
                        continue
                    raise ProviderDead(f"HTTP {r.status_code} after retries: "
                                       f"{r.text[:120]}")
                break
            try:
                data = r.json()
            except Exception as e:
                raise ProviderDead(f"non-JSON response: {e}")
            if isinstance(data, list):
                data = data[0] if data and isinstance(data[0], dict) else {}
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                msg = err.get("message", str(err)) if isinstance(err, dict) \
                    else str(err)
                low = msg.lower()
                if "not found" in low or "not supported" in low:
                    last = f"model {model}: {msg[:80]}"
                    continue
                raise ProviderDead(f"API error: {msg[:160]}")
            try:
                parts = data["candidates"][0]["content"]["parts"]
                return parts or []
            except Exception as e:
                last = f"bad response: {e}"
        raise ProviderDead(last or "no working Gemini model name")

    def _gemini_native_call(self, prov, system, contents, max_tokens):
        """Google's native generateContent API — the one the AQ.-style
        keys are actually for (key= URL parameter, per their console)."""
        import time
        models = [prov["model"]] + [
            m for m in getattr(config, "GEMINI_MODEL_FALLBACKS", [])
            if m != prov["model"]]
        last = None
        for model in models:
            url = (f"{prov['base']}/models/{model}:generateContent"
                   f"?key={prov['key']}")
            payload = {"contents": contents,
                       "generationConfig": {"maxOutputTokens": max_tokens}}
            if system:
                payload["systemInstruction"] = {"parts": [{"text": system}]}
            r = None
            for attempt in (1, 2, 3):
                try:
                    r = httpx.post(url, json=payload, timeout=90,
                                   headers={"x-goog-api-key": prov["key"]})
                except Exception as e:
                    raise ProviderDead(f"unreachable: {e}")
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < 3:
                        time.sleep(3 * attempt)
                        continue
                    raise ProviderDead(f"HTTP {r.status_code} after retries: "
                                       f"{r.text[:120]}")
                break
            try:
                data = r.json()
            except Exception as e:
                raise ProviderDead(f"non-JSON response: {e}")
            if isinstance(data, list):
                data = data[0] if data and isinstance(data[0], dict) else {}
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                msg = err.get("message", str(err)) if isinstance(err, dict) \
                    else str(err)
                if "not found" in msg.lower() or "not supported" in msg.lower():
                    last = f"model {model}: {msg[:80]}"
                    continue   # try the next model name
                raise ProviderDead(f"API error: {msg[:160]}")
            try:
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
                last = "empty reply"
            except Exception as e:
                last = f"bad response: {e}"
        raise ProviderDead(last or "no working Gemini model name")

    # ── the tool loop, provider-agnostic ────────

    def run_tool_loop(self, system, history, user_content, tools,
                      execute, on_text=None, max_rounds=10,
                      compact_system=None, compact_tools=None,
                      smart=False):
        """history: prior turns [{'role','content'(str)}...]
           user_content: str or Anthropic-style block list for THIS turn.
           execute(name, args) -> ToolResult (or str, legacy).
           compact_system/compact_tools: slimmer variants used for free
           providers whose per-minute token budgets a full-fat request
           can blow single-handedly. Claude gets the full version.
           Returns dict(text, tools_used, ran_out, provider, error,
                        tools_available).

           tools_available is the load-bearing field: False means NO tool
           could possibly have run this turn, so any action the model
           describes is fiction by construction. Callers must gate on it."""
        order = [n for n in config.LLM_PROVIDER_ORDER if _providers().get(n)]
        errors = []
        wanted_tools = bool(tools)

        # Tools executed across EVERY provider attempt in this turn.
        # _loop_with builds its own per-provider list, which is lost when
        # a provider dies mid-turn after already running a tool — the
        # caller then sees tools_used=[] for work that genuinely
        # happened. Wrapping execute here records it once, for real,
        # regardless of how many brains we cycle through.
        executed_all = []

        def _execute_tracked(_name, _args):
            executed_all.append(_name)
            return execute(_name, _args)

        # PASS 1 — providers that genuinely execute tools.
        # PASS 2 — text-only providers, and ONLY if no tools were wanted.
        # A tool-bearing turn never reaches a provider that can't run
        # tools, because "answered without the tools it needed" is the
        # exact shape of the hallucination bug.
        tool_capable = [n for n in order if _providers()[n].get("tools")]
        text_only = [n for n in order if not _providers()[n].get("tools")]
        attempt_order = tool_capable + ([] if wanted_tools else text_only)

        if wanted_tools and not tool_capable:
            return {"text": "", "tools_used": [], "ran_out": False,
                    "provider": None, "tools_available": False,
                    "error": "no tool-capable brain is configured (need a "
                             "GROQ_API_KEY or GEMINI_API_KEY)"}

        for name in attempt_order:
            prov = _providers()[name]
            if not prov["ok"]:
                errors.append(f"{name}: no API key found in environment")
                continue
            if prov["kind"] == "anthropic" and self.anthropic is None:
                errors.append("anthropic: client not initialised")
                continue
            if name == "anthropic":
                use_system, use_tools = system, tools
            else:
                use_system = compact_system or system
                use_tools = compact_tools if compact_tools is not None else tools
            # never hand tools to a provider that only pretends to run them
            if not prov.get("tools"):
                use_tools = None
            try:
                result = self._loop_with(name, prov, use_system, history,
                                         user_content, use_tools,
                                         _execute_tracked,
                                         on_text, max_rounds, smart=smart)
                self.active_provider = name
                result["provider"] = name
                result["tools_available"] = bool(use_tools)
                # union: this attempt's list plus anything that ran on an
                # earlier attempt that died before returning
                seen = list(dict.fromkeys(list(executed_all)
                                          + list(result.get("tools_used") or [])))
                result["tools_used"] = seen
                return result
            except ProviderDead as e:
                errors.append(f"{name}: {str(e)[:110]}")
                print(f"[LLM] provider {name} dead → next. ({str(e)[:120]})")
                continue

        # Every tool-capable brain failed on a turn that needed tools.
        # Answering anyway from a text-only brain would produce exactly
        # the fabricated "I did it" reply we are eliminating, so we don't.
        return {"text": "", "tools_used": list(dict.fromkeys(executed_all)),
                "ran_out": False,
                "provider": None, "tools_available": False,
                "error": " | ".join(errors) or "no providers configured"}

    def provider_status(self) -> str:
        """Human-readable table of every brain and whether it can work."""
        lines = ["BRAIN PROVIDERS (tried in this order):"]
        for name in config.LLM_PROVIDER_ORDER:
            prov = _providers().get(name)
            if not prov:
                continue
            if name == "anthropic":
                fast = getattr(config, "CLAUDE_MODEL_FAST", "")
                state = ("key found" if prov["ok"] and self.anthropic
                         else "NO KEY / client failed")
                if fast:
                    state += f" — fast: {fast}, smart: {config.CLAUDE_MODEL}"
            elif name == "ollama":
                state = f"will try {prov['base']} (local, only if installed)"
            elif name == "gemini":
                if prov["ok"]:
                    models, err = gemini_available_models()
                    if models:
                        state = (f"key found — {len(models)} usable model(s), "
                                 f"using {prov['model']}")
                        if config.GEMINI_MODEL not in models:
                            state += (f"  (config says "
                                      f"{config.GEMINI_MODEL!r}, which this "
                                      f"key CANNOT use — auto-switched)")
                    else:
                        state = f"key found but no usable models: {err[:90]}"
                else:
                    state = "NO KEY — env var GEMINI_API_KEY not visible to me"
            else:
                envname = "GROQ_API_KEY" if name == "groq" else "OPENROUTER_API_KEY"
                state = "key found" if prov["ok"] else \
                    f"NO KEY — {envname} not set (free key: " \
                    + ("console.groq.com" if name == "groq" else "openrouter.ai") + ")"
            active = "  ← answered last" if self.active_provider == name else ""
            lines.append(f"  {name}: {prov['model']} — {state}{active}")
        lines.append(
            "If a key you set shows as missing: setx only reaches NEW windows — "
            "close every terminal, open a fresh one, run the installer again "
            "(or reboot). Keys must be set for the same Windows user that runs me.")
        return "\n".join(lines)

    def _loop_with(self, name, prov, system, history, user_content,
                   tools, execute, on_text, max_rounds, smart=False):
        tools_used = []

        if prov["kind"] == "anthropic":
            messages = list(history) + [{"role": "user", "content": user_content}]
            for _ in range(max_rounds):
                resp = self._anthropic_call(system, messages, tools, 4096,
                                            smart=smart)
                tool_blocks = [b for b in resp.content
                               if getattr(b, "type", "") == "tool_use"]
                text_parts = [b.text for b in resp.content
                              if getattr(b, "type", "") == "text"]
                if resp.stop_reason == "tool_use" and tool_blocks:
                    interim = " ".join(text_parts).strip()
                    if interim and on_text:
                        on_text(interim)
                    messages.append({"role": "assistant", "content": resp.content})
                    results = []
                    for tb in tool_blocks:
                        tools_used.append(tb.name)
                        out = execute(tb.name, tb.input or {})
                        results.append({"type": "tool_result",
                                        "tool_use_id": tb.id,
                                        "content": _render_tool_output(out)})
                    messages.append({"role": "user", "content": results})
                    continue
                return {"text": " ".join(text_parts).strip(),
                        "tools_used": tools_used, "ran_out": False, "error": ""}
            return {"text": "", "tools_used": tools_used,
                    "ran_out": True, "error": ""}

        if prov["kind"] == "gemini-native":
            # chat + vision + NATIVE TOOL-CALLING (Gemini supports function
            # calling — this lets the smart free brain actually DO things,
            # not just describe them).
            contents = []
            for h in history[-8:]:
                contents.append({
                    "role": "model" if h["role"] == "assistant" else "user",
                    "parts": _blocks_to_gemini(h["content"])})
            contents.append({"role": "user",
                             "parts": _blocks_to_gemini(user_content)})
            gtools = _tools_to_gemini(tools) if tools else None
            for _ in range(max_rounds):
                parts = self._gemini_generate(prov, system, contents,
                                               gtools, 1024)
                fcalls = [p["functionCall"] for p in parts
                          if isinstance(p, dict) and "functionCall" in p]
                texts = [p["text"] for p in parts
                         if isinstance(p, dict) and p.get("text")]
                if fcalls:
                    interim = " ".join(texts).strip()
                    if interim and on_text:
                        on_text(interim)
                    contents.append({"role": "model", "parts": parts})
                    responses = []
                    for fc in fcalls:
                        fname = fc.get("name", "?")
                        fargs = fc.get("args") or {}
                        tools_used.append(fname)
                        out = execute(fname, fargs)
                        responses.append({"functionResponse": {
                            "name": fname,
                            "response": {"result": _render_tool_output(out)}}})
                    # v1beta REST only accepts roles 'user'/'model' — the
                    # function result goes back as a 'user' turn.
                    contents.append({"role": "user", "parts": responses})
                    continue
                return {"text": " ".join(texts).strip(),
                        "tools_used": tools_used, "ran_out": False, "error": ""}
            return {"text": "", "tools_used": tools_used,
                    "ran_out": True, "error": ""}

        # OpenAI-compatible providers — with model-hopping: if one model
        # is saturated (free lanes get crowded), try the next.
        model_candidates = prov.get("models") or [prov["model"]]
        last_exc = None
        for model_name in model_candidates:
            p2 = dict(prov)
            p2["model"] = model_name
            oa = [{"role": "system", "content": system}]
            for h in history[-8:]:            # token diet: recent turns only
                c = _blocks_to_openai(h["content"])
                if isinstance(c, str) and len(c) > 1500:
                    c = c[:1500] + "…"
                oa.append({"role": h["role"], "content": c})
            oa.append({"role": "user",
                       "content": _blocks_to_openai(user_content)})
            oa_tools = _tools_to_openai(tools) if tools else None
            tools_used = []
            try:
                glitches = 0
                for _ in range(max_rounds + 2):
                    try:
                        choice = self._openai_call(p2, oa, oa_tools, 1024)
                    except ToolCallGlitch as e:
                        glitches += 1
                        # THE BUG THAT CAUSED THE HALLUCINATIONS:
                        # this used to set `oa_tools = None` and re-ask the
                        # same question with the tools stripped out. The
                        # model, now unable to call anything, simply
                        # described what it would have done — and that
                        # narration was returned as a normal answer with
                        # tools_used=[]. Silent, and indistinguishable from
                        # real work.
                        #
                        # A model that cannot emit valid tool syntax is a
                        # DEAD provider for a tool-bearing turn. Fail over
                        # to the next tool-capable brain instead of
                        # quietly downgrading to storytelling.
                        if glitches >= 2:
                            raise ProviderDead(
                                f"could not produce a valid tool call after "
                                f"{glitches} attempts: {str(e)[:120]}")
                        continue
                    msg = choice.get("message", {})
                    calls = msg.get("tool_calls") or []
                    if choice.get("finish_reason") == "tool_calls" or calls:
                        if msg.get("content") and on_text:
                            on_text(str(msg["content"]).strip())
                        oa.append({"role": "assistant",
                                   "content": msg.get("content"),
                                   "tool_calls": calls})
                        for c in calls:
                            fn = c.get("function", {})
                            tname = fn.get("name", "?")
                            try:
                                targs = json.loads(fn.get("arguments") or "{}")
                            except Exception:
                                targs = {}
                            tools_used.append(tname)
                            out = execute(tname, targs)
                            oa.append({"role": "tool",
                                       "tool_call_id": c.get("id", ""),
                                       "content": _render_tool_output(out)})
                        continue
                    return {"text": str(msg.get("content") or "").strip(),
                            "tools_used": tools_used, "ran_out": False,
                            "error": ""}
                return {"text": "", "tools_used": tools_used,
                        "ran_out": True, "error": ""}
            except ProviderDead as e:
                last_exc = e
                continue   # next model candidate
        raise last_exc or ProviderDead("no model candidates worked")

    def generate_image(self, prompt, out_path):
        """Generate an image from a text prompt using Gemini's free
        image model (gemini-2.5-flash-image). Saves a PNG to out_path
        and returns the path, or raises with a clear reason."""
        import base64 as _b64
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "Image generation needs a Gemini key (free at "
                "aistudio.google.com/apikey) in keys.py as GEMINI_API_KEY.")
        model = getattr(config, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        url = (f"https://generativelanguage.googleapis.com/v1beta/"
               f"models/{model}:generateContent?key={key}")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        try:
            r = httpx.post(url, json=payload, timeout=180,
                           headers={"x-goog-api-key": key})
        except Exception as e:
            raise RuntimeError(f"could not reach the image service: {e}")
        if r.status_code != 200:
            raise RuntimeError(f"image API HTTP {r.status_code}: "
                               f"{r.text[:180]}")
        data = r.json()
        if isinstance(data, list):
            data = data[0] if data else {}
        if "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) \
                else str(err)
            raise RuntimeError(f"image API error: {msg[:180]}")
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except Exception:
            raise RuntimeError(f"unexpected image response: {str(data)[:180]}")
        for part in parts:
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                raw = _b64.b64decode(inline["data"])
                import os as _os
                _os.makedirs(_os.path.dirname(_os.path.abspath(out_path)),
                             exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(raw)
                return out_path
        raise RuntimeError("the model returned no image (it may have "
                           "refused the prompt)")

    # ── simple one-shot (Mind, small jobs) ──────

    def simple(self, system, user, max_tokens=400):
        res = self.run_tool_loop(system, [], user, [], lambda n, a: "",
                                 max_rounds=1)
        # run_tool_loop with no tools returns first text
        if res.get("text"):
            return res["text"]
        raise RuntimeError(res.get("error") or "no provider available")

    # ── vision (camera / images) ────────────────

    def describe_image(self, jpeg_bytes, prompt):
        content = [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/jpeg",
             "data": base64.b64encode(jpeg_bytes).decode()}},
            {"type": "text", "text": prompt},
        ]
        order = [n for n in config.LLM_PROVIDER_ORDER
                 if _providers().get(n, {}).get("vision")]
        errors = []
        for name in order:
            prov = _providers()[name]
            if not prov["ok"]:
                errors.append(f"{name}: no key")
                continue
            if prov["kind"] == "anthropic" and self.anthropic is None:
                errors.append("anthropic: client not initialised")
                continue
            try:
                res = self._loop_with(name, prov, "You are JARVIS.",
                                      [], content, [], lambda n, a: "",
                                      None, 1)
                if res.get("text"):
                    return res["text"]
                errors.append(f"{name}: empty reply")
            except ProviderDead as e:
                errors.append(f"{name}: {str(e)[:110]}")
        return ("I captured the image but every vision brain refused, sir:\n"
                + "\n".join(f"  • {e}" for e in errors)
                + "\nType 'test brains' for a full diagnostic.")

    def provider_test(self) -> str:
        """Ping every configured provider with a tiny request and report
        exactly what each one says. Turns guessing into data."""
        lines = ["BRAIN TEST (live ping of each provider):"]
        for name in config.LLM_PROVIDER_ORDER:
            prov = _providers().get(name)
            if not prov:
                continue
            if not prov["ok"]:
                lines.append(f"  {name}: SKIPPED — no key configured")
                continue
            if prov["kind"] == "anthropic" and self.anthropic is None:
                lines.append("  anthropic: SKIPPED — client not initialised")
                continue
            try:
                res = self._loop_with(name, prov, "Reply with exactly: OK",
                                      [], "ping", [], lambda n, a: "",
                                      None, 1)
                reply = (res.get("text") or "")[:40]
                lines.append(f"  {name}: WORKING — replied '{reply}'")
            except ProviderDead as e:
                lines.append(f"  {name}: FAILED — {str(e)[:130]}")
            except Exception as e:
                lines.append(f"  {name}: ERROR — {str(e)[:130]}")
        return "\n".join(lines)
