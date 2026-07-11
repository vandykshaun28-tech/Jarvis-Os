"""
browser_agent.py
────────────────
JARVIS's hands in the browser. Real clicking, typing and navigation via
Playwright — the browser window is VISIBLE so Shaun watches every move.

Install (once, with the venv's pip):
    pip install playwright
    playwright install chromium

Safety rules baked in:
  • SENSITIVE fields (passwords, card numbers, ID/passport, CVV) are
    NEVER filled by JARVIS. The fill tool refuses and tells the model to
    ask Shaun to type that field himself in the visible window, then
    say "done" to continue. Everything else JARVIS fills.
  • Every action returns what ACTUALLY happened (or the error), so the
    activity ledger and honesty guard stay truthful.
  • read_page() returns the page text PLUS a numbered list of inputs,
    buttons and links so the model can act on what is really there
    instead of guessing selectors.
"""

import re
import time
from pathlib import Path
from datetime import datetime


SENSITIVE = re.compile(
    r"pass(word|phrase)?|card ?number|credit ?card|cvv|cvc|expiry|"
    r"id ?number|passport|social ?security|ssn|pin\b|otp|one[- ]time",
    re.IGNORECASE)


class BrowserAgent:

    def __init__(self, on_status=None, screenshots_dir=None,
                 profile_dir=None):
        self.on_status = on_status or (lambda m: None)
        self.shots_dir = Path(screenshots_dir or ".")
        # Persistent profile: cookies + Google sign-in SURVIVE between
        # sessions. Sign in to vandykshaun28@gmail.com once in this
        # window and JARVIS's browser stays on that account forever.
        self.profile_dir = Path(profile_dir) if profile_dir else \
            (self.shots_dir.parent / "browser_profile")
        self._pw = None
        self.context = None
        self.page = None
        self.last_screenshot = None

    # ── lifecycle ────────────────────────────────
    def _ensure(self):
        """Lazy-start Playwright + a visible Chromium window with the
        persistent JARVIS profile (keeps Google/Shopify logins)."""
        if self.page is not None:
            try:
                _ = self.page.title()   # probe: still alive?
                return True
            except Exception:
                self.page = None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run (with the venv pip): "
                "pip install playwright  then:  playwright install chromium")
        if self._pw is None:
            self._pw = sync_playwright().start()
        alive = False
        try:
            alive = self.context is not None and self.context.pages is not None
        except Exception:
            alive = False
        if not alive:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            # Look like a normal Chrome, not an "automated test browser":
            #   • channel="chrome" uses the REAL installed Chrome
            #   • AutomationControlled off + no --enable-automation banner
            # Without these Google sign-in refuses with "this browser or
            # app may not be secure".
            kwargs = dict(
                user_data_dir=str(self.profile_dir),
                headless=False,
                no_viewport=True,
                args=["--start-maximized",
                      "--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            try:
                self.context = self._pw.chromium.launch_persistent_context(
                    channel="chrome", **kwargs)
            except Exception as e:
                print(f"[Browser] real Chrome unavailable ({e}) — "
                      f"falling back to bundled Chromium.")
                self.context = self._pw.chromium.launch_persistent_context(
                    **kwargs)
        self.page = self.context.pages[0] if self.context.pages \
            else self.context.new_page()
        return True

    def close(self) -> str:
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        self.context = None
        self.page = None
        return "Browser closed."

    # ── actions ──────────────────────────────────
    def goto(self, url: str) -> str:
        self._ensure()
        if not url.startswith("http"):
            url = "https://" + url
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(1.0)
        return f"On {self.page.url} — title: {self.page.title()!r}"

    def read_page(self) -> str:
        """Page text + interactive elements the model can act on."""
        self._ensure()
        title = self.page.title()
        url = self.page.url
        try:
            body = self.page.inner_text("body", timeout=8000)
        except Exception:
            body = "(could not read body text)"
        body = re.sub(r"\n{3,}", "\n\n", body)[:4000]

        elements = []
        try:
            for h in self.page.query_selector_all(
                    "input:visible, textarea:visible, select:visible")[:25]:
                t = h.get_attribute("type") or "text"
                if t == "hidden":
                    continue
                label = (h.get_attribute("placeholder")
                         or h.get_attribute("aria-label")
                         or h.get_attribute("name")
                         or h.get_attribute("id") or "?")
                elements.append(f"  INPUT [{t}] \"{label}\"")
            for h in self.page.query_selector_all(
                    "button:visible, [role=button]:visible, "
                    "input[type=submit]:visible")[:20]:
                txt = (h.inner_text() or h.get_attribute("value") or "").strip()
                if txt:
                    elements.append(f"  BUTTON \"{txt[:60]}\"")
            for h in self.page.query_selector_all("a:visible")[:20]:
                txt = (h.inner_text() or "").strip()
                if txt:
                    elements.append(f"  LINK \"{txt[:60]}\"")
        except Exception as e:
            elements.append(f"  (element scan failed: {e})")

        return (f"URL: {url}\nTITLE: {title}\n\n"
                f"INTERACTIVE ELEMENTS:\n" + "\n".join(elements[:50])
                + f"\n\nPAGE TEXT:\n{body}")

    def click(self, target: str) -> str:
        """Click by visible text first, CSS selector as fallback."""
        self._ensure()
        errors = []
        for finder in (
            lambda: self.page.get_by_role("button", name=target).first,
            lambda: self.page.get_by_role("link", name=target).first,
            lambda: self.page.get_by_text(target, exact=False).first,
            lambda: self.page.locator(target).first,
        ):
            try:
                loc = finder()
                loc.click(timeout=6000)
                time.sleep(0.8)
                return (f"Clicked {target!r}. Now on {self.page.url} "
                        f"— title: {self.page.title()!r}")
            except Exception as e:
                errors.append(str(e)[:80])
        return (f"Could not click {target!r}. Tried text, role and CSS. "
                f"Use browser_read to see what is actually on the page. "
                f"Last error: {errors[-1] if errors else '?'}")

    def fill(self, field: str, value: str) -> str:
        """Fill an input found by placeholder / label / name / CSS.
        REFUSES sensitive fields — Shaun types those himself."""
        self._ensure()
        if SENSITIVE.search(field) or SENSITIVE.search(value or ""):
            return ("REFUSED — this looks like a sensitive field (password / "
                    "card / ID / OTP). Tell Shaun exactly which field to fill "
                    "in the browser window himself, wait for him to say "
                    "'done', then continue with the next step.")
        errors = []
        for finder in (
            lambda: self.page.get_by_placeholder(field).first,
            lambda: self.page.get_by_label(field).first,
            lambda: self.page.locator(f"input[name='{field}']").first,
            lambda: self.page.locator(field).first,
        ):
            try:
                loc = finder()
                loc.fill(value, timeout=6000)
                return f"Filled {field!r} with {value[:40]!r}."
            except Exception as e:
                errors.append(str(e)[:80])
        return (f"Could not find field {field!r}. Use browser_read to see "
                f"the real field names. Last error: "
                f"{errors[-1] if errors else '?'}")

    def press(self, key: str) -> str:
        self._ensure()
        self.page.keyboard.press(key)
        time.sleep(0.8)
        return f"Pressed {key}. Now on {self.page.url}"

    def screenshot(self) -> str:
        self._ensure()
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        path = self.shots_dir / \
            f"browser_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        self.page.screenshot(path=str(path))
        self.last_screenshot = str(path)
        return f"Browser screenshot saved to {path}"
