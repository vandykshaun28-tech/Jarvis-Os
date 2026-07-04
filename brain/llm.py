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

import httpx

import config


class ProviderDead(Exception):
    """This provider can't serve us (credits/auth/unreachable) — try next."""


def _providers():
    """Provider table, built fresh so env-var changes are picked up."""
    return {
        "anthropic": {"kind": "anthropic", "vision": True,
                      "model": config.CLAUDE_MODEL,
                      "ok": bool(os.environ.get("ANTHROPIC_API_KEY"))},
        "groq":      {"kind": "openai", "vision": False,
                      "base": "https://api.groq.com/openai/v1",
                      "model": config.GROQ_MODEL,
                      "key": os.environ.get("GROQ_API_KEY", ""),
                      "ok": bool(os.environ.get("GROQ_API_KEY"))},
        "gemini":    {"kind": "gemini-native", "vision": True,
                      "base": "https://generativelanguage.googleapis.com/v1beta",
                      "model": config.GEMINI_MODEL,
                      "key": os.environ.get("GEMINI_API_KEY", ""),
                      "ok": bool(os.environ.get("GEMINI_API_KEY"))},
        "ollama":    {"kind": "openai", "vision": False,
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


class UniversalLLM:

    def __init__(self, anthropic_client=None):
        self.anthropic = anthropic_client
        self.active_provider = None   # last provider that worked

    # ── low-level single calls ──────────────────

    def _anthropic_call(self, system, messages, tools, max_tokens):
        try:
            kwargs = dict(model=config.CLAUDE_MODEL, max_tokens=max_tokens,
                          system=system, messages=messages)
            if tools:
                kwargs["tools"] = tools
            return self.anthropic.messages.create(**kwargs)
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
                raise ProviderDead(f"API error: {msg[:160]}")
            try:
                return data["choices"][0]
            except Exception as e:
                raise ProviderDead(f"bad response: {e} — {r.text[:120]}")

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
                      execute, on_text=None, max_rounds=10):
        """history: prior turns [{'role','content'(str)}...]
           user_content: str or Anthropic-style block list for THIS turn.
           execute(name, args) -> str result.
           Returns dict(text, tools_used, ran_out, provider, error)."""
        order = [n for n in config.LLM_PROVIDER_ORDER if _providers().get(n)]
        errors = []
        for name in order:
            prov = _providers()[name]
            if not prov["ok"]:
                errors.append(f"{name}: no API key found in environment")
                continue
            if prov["kind"] == "anthropic" and self.anthropic is None:
                errors.append("anthropic: client not initialised")
                continue
            try:
                result = self._loop_with(name, prov, system, history,
                                         user_content, tools, execute,
                                         on_text, max_rounds)
                self.active_provider = name
                result["provider"] = name
                return result
            except ProviderDead as e:
                errors.append(f"{name}: {str(e)[:110]}")
                print(f"[LLM] provider {name} dead → next. ({str(e)[:120]})")
                continue
        return {"text": "", "tools_used": [], "ran_out": False,
                "provider": None,
                "error": " | ".join(errors) or "no providers configured"}

    def provider_status(self) -> str:
        """Human-readable table of every brain and whether it can work."""
        lines = ["BRAIN PROVIDERS (tried in this order):"]
        for name in config.LLM_PROVIDER_ORDER:
            prov = _providers().get(name)
            if not prov:
                continue
            if name == "anthropic":
                state = ("key found" if prov["ok"] and self.anthropic
                         else "NO KEY / client failed")
            elif name == "ollama":
                state = f"will try {prov['base']} (local, only if installed)"
            elif name == "gemini":
                state = ("key found (chat & vision — no tool use)"
                         if prov["ok"] else
                         "NO KEY — env var GEMINI_API_KEY not visible to me")
            else:
                state = "key found" if prov["ok"] else \
                    "NO KEY — env var GROQ_API_KEY not visible to me"
            active = "  ← answered last" if self.active_provider == name else ""
            lines.append(f"  {name}: {prov['model']} — {state}{active}")
        lines.append(
            "If a key you set shows as missing: setx only reaches NEW windows — "
            "close every terminal, open a fresh one, run the installer again "
            "(or reboot). Keys must be set for the same Windows user that runs me.")
        return "\n".join(lines)

    def _loop_with(self, name, prov, system, history, user_content,
                   tools, execute, on_text, max_rounds):
        tools_used = []

        if prov["kind"] == "anthropic":
            messages = list(history) + [{"role": "user", "content": user_content}]
            for _ in range(max_rounds):
                resp = self._anthropic_call(system, messages, tools, 1024)
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
                                        "content": str(out)[:3000]})
                    messages.append({"role": "user", "content": results})
                    continue
                return {"text": " ".join(text_parts).strip(),
                        "tools_used": tools_used, "ran_out": False, "error": ""}
            return {"text": "", "tools_used": tools_used,
                    "ran_out": True, "error": ""}

        if prov["kind"] == "gemini-native":
            # chat & vision, no tool-calling (Groq/Claude handle tools)
            contents = []
            for h in history:
                contents.append({
                    "role": "model" if h["role"] == "assistant" else "user",
                    "parts": _blocks_to_gemini(h["content"])})
            contents.append({"role": "user",
                             "parts": _blocks_to_gemini(user_content)})
            text = self._gemini_native_call(prov, system, contents, 1024)
            return {"text": text, "tools_used": [], "ran_out": False,
                    "error": ""}

        # OpenAI-compatible providers
        oa = [{"role": "system", "content": system}]
        for h in history:
            oa.append({"role": h["role"],
                       "content": _blocks_to_openai(h["content"])})
        oa.append({"role": "user", "content": _blocks_to_openai(user_content)})
        oa_tools = _tools_to_openai(tools) if tools else None

        for _ in range(max_rounds):
            choice = self._openai_call(prov, oa, oa_tools, 1024)
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
                               "content": str(out)[:3000]})
                continue
            return {"text": str(msg.get("content") or "").strip(),
                    "tools_used": tools_used, "ran_out": False, "error": ""}
        return {"text": "", "tools_used": tools_used,
                "ran_out": True, "error": ""}

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
