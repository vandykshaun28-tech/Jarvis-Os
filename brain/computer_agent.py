"""
computer_agent.py
─────────────────
JARVIS's HANDS AND EYES — the computer-use agent.

This is what lets JARVIS actually operate the PC like a person:
he takes a screenshot (eyes), sends it to the Claude vision brain,
the brain decides an action (click here, type this, press that),
JARVIS moves the REAL cursor — visibly gliding across the screen —
performs the action, takes a fresh screenshot to VERIFY it worked,
and repeats until the task is done.

    see → think → move cursor → click/type → verify → repeat

Safety:
  • pyautogui FAILSAFE — slam the mouse into the TOP-LEFT corner of the
    screen and every action aborts instantly.
  • Hard step budget (default 25) so a confused loop can't run forever.
  • Never types into password/card/OTP fields — asks Shaun instead.
  • Narrates every action to the chat so Shaun can watch him work.

Uses the SMART Claude tier (vision + judgement). Each step costs one
vision call, so a typical task runs a few cents — the cost tracker
records every token as always.
"""

import time

import config


SYSTEM = """You are JARVIS, operating Shaun's Windows PC by looking at \
screenshots and issuing ONE action at a time through the `computer` tool.

RULES:
- The screenshot is your ONLY source of truth. Look carefully before acting.
- Coordinates (x, y) are pixels in the screenshot you were just shown.
  Aim for the CENTRE of the thing you want to click.
- One action per turn. After each action you receive a fresh screenshot —
  VERIFY your last action worked before moving on. If it didn't, try a
  different approach (different position, keyboard shortcut, scroll first).
- Prefer keyboard shortcuts when they're more reliable than clicking
  (e.g. ctrl+s to save, enter to submit, win to open Start).
- To launch an app, use the Start menu: press 'win', type the app name,
  press 'enter'.
- NEVER type into password, card-number, CVV, ID-number or OTP fields.
  Use action 'ask' to have Shaun enter those himself, then continue.
- If something unexpected appears (popup, dialog), deal with it first.
- When the task is genuinely complete and VERIFIED by the final
  screenshot, use action 'done' with a short summary.
- If the task is impossible or you are stuck after several attempts,
  use action 'fail' and explain what you saw.
- Be decisive. Do not re-take stock endlessly — act."""

COMPUTER_TOOL = {
    "name": "computer",
    "description": "Perform ONE action on the PC, then receive a fresh "
                   "screenshot showing the result.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["click", "double_click", "right_click",
                                "move", "drag", "type", "key", "scroll",
                                "wait", "ask", "done", "fail"]},
            "x": {"type": "integer", "description": "Pixel x in the screenshot (click/move/drag start/scroll)"},
            "y": {"type": "integer", "description": "Pixel y in the screenshot"},
            "x2": {"type": "integer", "description": "Drag end x"},
            "y2": {"type": "integer", "description": "Drag end y"},
            "text": {"type": "string",
                     "description": "Text to type (for 'type'), question for "
                                    "'ask', summary for 'done'/'fail'"},
            "keys": {"type": "string",
                     "description": "Key or combo for 'key', e.g. 'enter', "
                                    "'ctrl+s', 'alt+tab', 'win'"},
            "amount": {"type": "integer",
                       "description": "Scroll clicks: positive=up, negative=down (for 'scroll')"},
            "seconds": {"type": "number", "description": "Seconds for 'wait' (max 10)"},
            "reason": {"type": "string",
                       "description": "One short line: what you see and why this action"},
        },
        "required": ["action"],
    },
}

SENSITIVE = ("password", "passcode", "card number", "cvv", "cvc",
             "otp", "one-time", "id number", "pin ")


class ComputerAgent:
    """The vision-action loop. Built on the raw Anthropic client because
    every round carries a screenshot image — this loop is specialised."""

    def __init__(self, client, pc, cost_tracker=None, on_status=None):
        self.client = client          # Anthropic client (must support vision)
        self.pc = pc                  # PCControl — the actual hands
        self.cost_tracker = cost_tracker
        self.on_status = on_status
        self.busy = False

    def _say(self, msg):
        if self.on_status:
            try:
                self.on_status(f"→ [hands] {msg}")
            except Exception:
                pass
        print(f"[ComputerAgent] {msg}")

    def _shot(self):
        """Fresh screenshot as an Anthropic image block + scale factors."""
        r = self.pc.screenshot_b64(max_width=1280)
        if not r:
            return None, 1.0, 1.0, ""
        b64, iw, ih, sw, sh = r
        block = {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg",
                            "data": b64}}
        note = f"(screenshot is {iw}x{ih} pixels)"
        return block, sw / iw, sh / ih, note

    def _record_cost(self, resp, model):
        if self.cost_tracker is not None:
            try:
                u = resp.usage
                self.cost_tracker.record(model, u.input_tokens, u.output_tokens)
            except Exception:
                pass

    # ── the loop ────────────────────────────────────────────────────

    def run(self, task: str, max_steps: int = 25) -> str:
        if self.client is None:
            return ("I need the Claude brain (vision) to operate the screen, "
                    "sir — no Anthropic key is configured.")
        if self.pc is None:
            return "PC control is offline, sir — I have no hands."
        if self.busy:
            return "I'm already busy operating the screen, sir. One task at a time."

        self.busy = True
        model = config.CLAUDE_MODEL          # SMART tier: vision + judgement
        system = SYSTEM
        gacct = (getattr(config, "GOOGLE_ACCOUNT", "") or "").strip()
        if gacct:
            system += (f"\n- ACCOUNT RULE: when any Google sign-in or "
                       f"account picker appears, ALWAYS choose {gacct} — "
                       f"never any other account.")
        actions_taken = []
        try:
            self._say(f"Taking control of the screen: {task}")
            shot, fx, fy, note = self._shot()
            if shot is None:
                return "I couldn't take a screenshot, sir — is pyautogui installed?"

            messages = [{"role": "user", "content": [
                {"type": "text", "text": f"TASK: {task}\n\nHere is the current "
                                         f"screen {note}. Begin."},
                shot,
            ]}]

            for step in range(1, max_steps + 1):
                resp = self.client.messages.create(
                    model=model, max_tokens=1024, system=system,
                    tools=[COMPUTER_TOOL], tool_choice={"type": "tool", "name": "computer"},
                    messages=messages)
                self._record_cost(resp, model)

                tool = next((b for b in resp.content
                             if getattr(b, "type", "") == "tool_use"), None)
                if tool is None:
                    text = " ".join(b.text for b in resp.content
                                    if getattr(b, "type", "") == "text").strip()
                    return text or "I lost my train of thought on screen, sir."

                a = tool.input or {}
                act = a.get("action", "")
                reason = a.get("reason", "")
                if reason:
                    self._say(f"step {step}: {reason}")

                # terminal actions
                if act == "done":
                    summary = a.get("text", "Task complete.")
                    self._say("Done.")
                    return f"{summary} ({step - 1} actions taken, sir.)"
                if act == "fail":
                    return ("I couldn't finish that on screen, sir. "
                            + a.get("text", "")).strip()
                if act == "ask":
                    q = a.get("text", "I need you to do the sensitive part "
                                      "yourself, sir.")
                    return (f"PAUSED FOR YOU, SIR: {q} — tell me to "
                            f"continue when you've done it.")

                # guard: never type secrets
                if act == "type":
                    low = (a.get("text") or "").lower() + " " + reason.lower()
                    if any(s in low for s in SENSITIVE):
                        return ("That looks like a sensitive field, sir — "
                                "please type it yourself, then ask me to continue.")

                result = self._do(act, a, fx, fy)
                actions_taken.append(f"{act}: {result}")
                self._say(result)

                # settle, then verify with fresh eyes
                time.sleep(0.9 if act in ("click", "double_click", "key") else 0.5)
                shot, fx, fy, note = self._shot()
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tool.id,
                     "content": [
                         {"type": "text",
                          "text": f"Result: {result}\nFresh screenshot {note} — "
                                  f"verify before your next action."},
                         shot,
                     ]},
                ]})

                # token diet: only keep the LAST screenshot in history —
                # old screenshots are stale and expensive
                self._strip_old_images(messages)

            return (f"I ran out of my {max_steps}-step budget, sir. "
                    f"Progress so far: {'; '.join(actions_taken[-5:])}")
        except Exception as e:
            if "fail-safe" in str(e).lower() or "failsafe" in str(e).lower():
                return "You grabbed the mouse to the corner — aborted, sir."
            return f"Screen control error, sir: {e}"
        finally:
            self.busy = False

    # ── executing one action with the real hands ────────────────────

    def _do(self, act, a, fx, fy):
        """Scale screenshot pixels → real screen pixels, then act."""
        def X(k="x"): return int(round(a.get(k, 0) * fx))
        def Y(k="y"): return int(round(a.get(k, 0) * fy))
        pc = self.pc
        try:
            if act == "click":
                return pc.click_at(X(), Y())
            if act == "double_click":
                return pc.double_click_at(X(), Y())
            if act == "right_click":
                return pc.right_click_at(X(), Y())
            if act == "move":
                return pc.move_mouse(X(), Y())
            if act == "drag":
                return pc.drag_to(X(), Y(), X("x2"), Y("y2"))
            if act == "type":
                return pc.type_text(a.get("text", ""))
            if act == "key":
                combo = (a.get("keys") or "").replace(" ", "")
                return pc.press_keys(*combo.split("+"))
            if act == "scroll":
                amt = int(a.get("amount", -3))
                if "x" in a and "y" in a:
                    return pc.scroll_wheel(amt, X(), Y())
                return pc.scroll_wheel(amt)
            if act == "wait":
                secs = min(float(a.get("seconds", 1)), 10.0)
                time.sleep(secs)
                return f"Waited {secs:g}s."
            return f"Unknown action '{act}'."
        except Exception as e:
            return f"Action '{act}' failed: {e}"

    @staticmethod
    def _strip_old_images(messages):
        """Keep only the newest screenshot; replace older ones with a stub."""
        seen_last = False
        for m in reversed(messages):
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    inner = block.get("content")
                    if not isinstance(inner, list):
                        continue
                    has_img = any(isinstance(b, dict) and b.get("type") == "image"
                                  for b in inner)
                    if not has_img:
                        continue
                    if not seen_last:
                        seen_last = True          # newest — keep it
                    else:
                        block["content"] = [
                            b for b in inner
                            if not (isinstance(b, dict) and b.get("type") == "image")
                        ] + [{"type": "text", "text": "(older screenshot removed)"}]
