"""
verify_phone_ui.py — render the phone page in a REAL browser and check it.

WHY THIS EXISTS: the phone UI was shipped twice without ever being
rendered. Both times it was broken in a way no amount of reading the
code would have caught — most recently a panel that hid itself with
transform:translateY(105%), which moves an element down by 105% of ITS
OWN height. Empty, that was ~85px: nowhere near enough to clear the
screen, so it sat directly on top of the message box. Shaun saw a blue
bar where the composer should be.

Checking "is the input covered" needs layout, and layout needs a
browser. elementFromPoint over the composer answers in one line what
staring at CSS could not.

Run:  python verify_phone_ui.py
Needs playwright + chromium; skips cleanly if they are not installed.
"""

import os
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

FAILS = []


def chk(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def _stub_qt():
    if "PySide6" in sys.modules:
        return
    q = types.ModuleType("PySide6")
    qc = types.ModuleType("PySide6.QtCore")

    class _S:
        def __init__(s, *a, **k): pass
        def __get__(s, o, t=None): return s
        def connect(s, *a, **k): pass
        def emit(s, *a, **k): pass

    class _O:
        def __init__(s, *a, **k): pass

    qc.QObject, qc.Signal, qc.QTimer = _O, _S, _O
    qc.Qt = types.SimpleNamespace()
    qc.QThread = _O
    q.QtCore = qc
    sys.modules["PySide6"] = q
    sys.modules["PySide6.QtCore"] = qc


def _chromium_path():
    for base in ("/opt/pw-browsers",):
        p = Path(base)
        if not p.exists():
            continue
        for d in sorted(p.glob("chromium-*")):
            exe = d / "chrome-linux" / "chrome"
            if exe.exists():
                return str(exe)
    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — skipping the phone UI check.")
        print("  pip install playwright && playwright install chromium")
        return 0

    _stub_qt()
    os.environ.setdefault("PHONE_KEY", "verify_key")
    key = os.environ["PHONE_KEY"]

    from core.session import SharedSession
    import core.phone_server as ps
    import tempfile

    class _Brain:
        current_activity = "idle"
        memory = researcher = cost_tracker = None

        def __init__(self):
            self.session = SharedSession(
                Path(tempfile.mkdtemp()) / "s.json")

        def show_panel(self, *a, **k): pass
        def process(self, t, files=None, source="pc"): return "ok"
        def identify_image(self, j, q=""): return "That's a turbo, sir."

    ps.start_phone_server(_Brain())
    time.sleep(2.5)

    launch = {}
    exe = _chromium_path()
    if exe:
        launch["executable_path"] = exe

    print("=== PHONE UI (rendered) ===")
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(**launch)
        except Exception as e:
            print(f"could not launch chromium ({e}) — skipping.")
            return 0
        pg = b.new_page(viewport={"width": 390, "height": 844})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("http://127.0.0.1:8500/", wait_until="networkidle")
        pg.evaluate(f"localStorage.setItem('jarvis_key','{key}')")
        pg.reload(wait_until="networkidle")
        time.sleep(1.2)

        chk("no uncaught JS errors", not errs, str(errs[:2]))

        r = pg.evaluate("""() => {
          const i=document.getElementById('input');
          if(!i) return {missing:true};
          const b=i.getBoundingClientRect();
          const top=document.elementFromPoint(b.left+b.width/2, b.top+b.height/2);
          return {h:b.height,
                  covered:(top && top.id!=='input')?(top.id||top.tagName):null};
        }""")
        chk("composer exists", not r.get("missing"))
        chk("composer is not covered by anything",
            r.get("covered") is None, f"top element: {r.get('covered')}")
        start = r.get("h", 0)

        pg.click("#input")
        pg.type("#input", "a long single line with no newlines at all that "
                          "has to wrap over several lines to prove the box "
                          "grows with wrapped text and not just newlines",
                delay=1)
        time.sleep(0.4)
        grown = pg.evaluate(
            "() => document.getElementById('input').getBoundingClientRect().height")
        chk("composer grows with WRAPPED text (not just newlines)",
            grown > start + 10, f"{start:.0f}px -> {grown:.0f}px")

        pg.evaluate("""() => { const i=document.getElementById('input');
            i.value='line\\n'.repeat(60); i.dispatchEvent(new Event('input')); }""")
        time.sleep(0.3)
        cap = pg.evaluate("""() => { const i=document.getElementById('input');
            return {h:i.getBoundingClientRect().height,
                    ov:getComputedStyle(i).overflowY, vh:window.innerHeight}; }""")
        chk("caps instead of eating the screen",
            cap["h"] < cap["vh"] * 0.40, f"{cap['h']:.0f}px of {cap['vh']}px")
        chk("scrolls internally once capped", cap["ov"] == "auto", cap["ov"])

        pg.evaluate("""() => { const i=document.getElementById('input');
            i.value=''; i.dispatchEvent(new Event('input'));
            showShelf('TEST','body',''); }""")
        time.sleep(0.5)
        sh = pg.evaluate("""() => { const s=document.getElementById('shelf');
            const i=document.getElementById('input').getBoundingClientRect();
            const top=document.elementFromPoint(i.left+i.width/2, i.top+i.height/2);
            return {vis:getComputedStyle(s).visibility,
                    covered:(top&&top.id!=='input')?(top.id||top.tagName):null}; }""")
        chk("panel opens when she shows something", sh["vis"] == "visible")
        chk("panel does NOT cover the composer while open",
            sh["covered"] is None, f"top: {sh['covered']}")

        pg.evaluate("() => document.getElementById('shelfclose').click()")
        time.sleep(0.5)
        chk("panel hides fully again",
            pg.evaluate("() => getComputedStyle(document.getElementById('shelf')).visibility")
            == "hidden")

        out = Path(__file__).parent / "memory" / "phone_ui_check.png"
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(out))
            print(f"\n  screenshot: {out}")
        except Exception:
            pass
        b.close()

    print(f"\nRESULT: {len(FAILS)} failed"
          + (f" -> {', '.join(FAILS)}" if FAILS else " — all good"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
