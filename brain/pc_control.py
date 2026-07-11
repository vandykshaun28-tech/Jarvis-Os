import os, subprocess, time, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import pyautogui
    pyautogui.FAILSAFE = True    # slam mouse to top-left corner = instant abort
    pyautogui.PAUSE = 0.05
    PYGUI_OK = True
except:
    PYGUI_OK = False

try:
    import psutil
    PSUTIL_OK = True
except:
    PSUTIL_OK = False

CREATE_NO_WINDOW = 0x08000000

class PCControl:
    def __init__(self, on_status=None):
        self.on_status = on_status
        self.last_screenshot = None
        print("[PC] PC Control engine online.")

    def show_desktop(self):
        if PYGUI_OK: pyautogui.hotkey("win", "d")
        return "Showing desktop, sir."

    def lock_pc(self):
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], creationflags=CREATE_NO_WINDOW)
        return "Locking workstation, sir."

    def mute(self):
        if PYGUI_OK: pyautogui.hotkey("volumemute")
        return "Muted, sir."

    def volume_up(self, steps=5):
        if PYGUI_OK:
            for _ in range(steps): pyautogui.hotkey("volumeup"); time.sleep(0.05)
        return "Volume up, sir."

    def volume_down(self, steps=5):
        if PYGUI_OK:
            for _ in range(steps): pyautogui.hotkey("volumedown"); time.sleep(0.05)
        return "Volume down, sir."

    def shutdown_pc(self, delay=60):
        subprocess.Popen(["shutdown", "/s", "/t", str(delay)], creationflags=CREATE_NO_WINDOW)
        return f"Shutting down in {delay}s, sir."

    def cancel_shutdown(self):
        subprocess.Popen(["shutdown", "/a"], creationflags=CREATE_NO_WINDOW)
        return "Shutdown cancelled, sir."

    def restart_pc(self, delay=60):
        subprocess.Popen(["shutdown", "/r", "/t", str(delay)], creationflags=CREATE_NO_WINDOW)
        return f"Restarting in {delay}s, sir."

    def sleep_pc(self):
        subprocess.Popen(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            creationflags=CREATE_NO_WINDOW,
        )
        return "Putting the PC to sleep, sir."

    def screenshot(self):
        if not PYGUI_OK: return "Not available, sir."
        d = config.SCREENSHOTS_DIR
        d.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        p = str(d / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        pyautogui.screenshot().save(p)
        self.last_screenshot = p
        return f"Screenshot saved to {p}"

    def type_text(self, text):
        """Type into the focused window. Plain short text is typed
        key-by-key (visible, human-like). Anything long or with special
        characters (unicode, symbols pyautogui can't press) goes in via
        clipboard-paste — reliable for EVERYTHING."""
        if not PYGUI_OK: return "Not available, sir."
        text = str(text)
        time.sleep(0.4)
        simple = all(32 <= ord(c) < 127 or c in "\n\t" for c in text)
        if simple and len(text) <= 200:
            pyautogui.typewrite(text, interval=0.03)
        else:
            self.set_clipboard(text)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.25)
        return f"Typed: {text[:40]}"

    # ── MOUSE — real cursor control (the hands) ─────────────────────
    # These move the ACTUAL cursor, visibly, like a person at the desk.
    # Safety: pyautogui.FAILSAFE is on — slamming the mouse into the
    # top-left corner of the screen aborts any action instantly.

    def screen_size(self):
        if not PYGUI_OK: return (0, 0)
        s = pyautogui.size()
        return (s.width, s.height)

    def mouse_position(self):
        if not PYGUI_OK: return (0, 0)
        p = pyautogui.position()
        return (p.x, p.y)

    def move_mouse(self, x, y, duration=0.35):
        """Glide the cursor to (x, y) — visible, human-like movement."""
        if not PYGUI_OK: return "Mouse control not available, sir."
        w, h = self.screen_size()
        x = max(1, min(int(x), w - 2))   # keep out of the failsafe corner
        y = max(1, min(int(y), h - 2))
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeOutQuad)
        return f"Cursor at ({x}, {y})."

    def click_at(self, x=None, y=None, button="left", clicks=1):
        """Move the cursor there (visibly) and click. No coords = click here."""
        if not PYGUI_OK: return "Mouse control not available, sir."
        if x is not None and y is not None:
            self.move_mouse(x, y)
            time.sleep(0.08)
        pyautogui.click(button=button, clicks=clicks,
                        interval=0.12 if clicks > 1 else 0.0)
        p = pyautogui.position()
        what = {("left", 1): "Clicked", ("left", 2): "Double-clicked",
                ("right", 1): "Right-clicked"}.get((button, clicks),
                                                   f"{button}-clicked x{clicks}")
        return f"{what} at ({p.x}, {p.y})."

    def double_click_at(self, x=None, y=None):
        return self.click_at(x, y, button="left", clicks=2)

    def right_click_at(self, x=None, y=None):
        return self.click_at(x, y, button="right", clicks=1)

    def drag_to(self, x1, y1, x2, y2, duration=0.6):
        """Press at (x1,y1), drag to (x2,y2), release."""
        if not PYGUI_OK: return "Mouse control not available, sir."
        self.move_mouse(x1, y1)
        time.sleep(0.1)
        pyautogui.dragTo(int(x2), int(y2), duration=duration, button="left")
        return f"Dragged from ({x1}, {y1}) to ({x2}, {y2})."

    def scroll_wheel(self, amount, x=None, y=None):
        """Scroll at a position. Positive = up, negative = down."""
        if not PYGUI_OK: return "Mouse control not available, sir."
        if x is not None and y is not None:
            self.move_mouse(x, y, duration=0.2)
        pyautogui.scroll(int(amount))
        return f"Scrolled {'up' if amount > 0 else 'down'} {abs(int(amount))}."

    def press_keys(self, *keys):
        """Press a key or combo, e.g. press_keys('ctrl','s') or ('enter',)."""
        if not PYGUI_OK: return "Keyboard control not available, sir."
        keys = [str(k).lower().strip() for k in keys if str(k).strip()]
        if not keys: return "No keys given, sir."
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return f"Pressed {'+'.join(keys)}."

    def screenshot_b64(self, max_width=1280):
        """Screenshot → (base64 JPEG, img_w, img_h, screen_w, screen_h).
        Downscaled so the vision brain gets a crisp-but-cheap image;
        the computer agent scales coordinates back up to real pixels."""
        if not PYGUI_OK: return None
        import base64, io
        img = pyautogui.screenshot()
        sw, sh = img.size
        if sw > max_width:
            img = img.resize((max_width, int(sh * max_width / sw)))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return (b64, img.size[0], img.size[1], sw, sh)

    def open_url(self, url):
        if not url.startswith("http"): url = "https://" + url
        subprocess.Popen(["start", url], shell=True, creationflags=CREATE_NO_WINDOW)
        return f"Opening {url}, sir."

    def google_search(self, query):
        return self.open_url("https://www.google.com/search?q=" + query.replace(" ", "+"))

    def get_system_info(self):
        if not PSUTIL_OK: return "Not available, sir."
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        return f"CPU: {cpu}% | RAM: {ram.percent}% | Disk: {disk.percent}%"

    def run_command(self, cmd):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
            return (r.stdout or r.stderr).strip()[:300] or "Done, sir."
        except Exception as e:
            return str(e)

    def search_files(self, query):
        results = []
        for root, dirs, files in os.walk(str(Path.home())):
            dirs[:] = [d for d in dirs if d not in {"AppData", "__pycache__", ".git"}][:3]
            for f in files:
                if query.lower() in f.lower(): results.append(os.path.join(root, f))
            if len(results) >= 8: break
        return "\n".join(results[:8]) if results else "No files found, sir."

    # ── GENERAL APP / FILE OPENING ──────────────────────────────────
    # Known aliases for apps whose process name or store-app id doesn't
    # match what you'd naturally say. Anything not in here still works —
    # it just falls through to Windows' own app-name resolution.
    APP_ALIASES = {
        "calculator":        "calc",
        "calc":               "calc",
        "notepad":            "notepad",
        "explorer":           "explorer",
        "file explorer":      "explorer",
        "vs code":            "code",
        "vscode":             "code",
        "visual studio code": "code",
        "chrome":             "chrome",
        "google chrome":      "chrome",
        "firefox":            "firefox",
        "edge":               "msedge",
        "spotify":            "spotify:",
        "discord":            "discord:",
        "obsidian":           "obsidian://open",
        "task manager":       "taskmgr",
        "control panel":      "control",
        "settings":           "ms-settings:",
        "paint":              "mspaint",
        "word":               "winword",
        "excel":              "excel",
        "powerpoint":         "powerpnt",
        "terminal":           "wt",
        "command prompt":     "cmd",
        "powershell":         "powershell",
        "cmd":                "cmd",
        "registry editor":    "regedit",
        "device manager":     "devmgmt.msc",
        "snipping tool":      "snippingtool",
    }

    def open_anything(self, name: str):
        """
        Best-effort 'open X' for apps, files, folders, or URLs in one call.
        Tries, in order:
          1. A literal path that exists on disk (file or folder)
          2. A URL (if it looks like one)
          3. A known alias (calculator, vs code, spotify, etc.)
          4. Raw `start <name>` — lets Windows resolve installed app names,
             UWP/Store apps, and anything on PATH that the above missed.
        """
        if not name or not name.strip():
            return "I need something to open, sir."
        name = name.strip()

        # 1) literal existing path
        p = Path(name)
        if p.exists():
            try:
                os.startfile(str(p))
                kind = "folder" if p.is_dir() else "file"
                return f"Opening {kind} {p.name}, sir."
            except Exception as e:
                return f"Found {p} but couldn't open it, sir: {e}"

        # 2) looks like a URL
        if name.lower().startswith(("http://", "https://", "www.")):
            return self.open_url(name)
        if "." in name and " " not in name and "/" not in name and "\\" not in name \
                and not name.lower().endswith((".exe", ".py", ".txt")):
            # heuristic: "github.com" style bare domain
            return self.open_url(name)

        # 3) known alias
        key = name.lower().strip()
        target = self.APP_ALIASES.get(key)
        if target:
            try:
                subprocess.Popen(f"start {target}", shell=True, creationflags=CREATE_NO_WINDOW)
                return f"Opening {name}, sir."
            except Exception as e:
                return f"Couldn't open {name}, sir: {e}"

        # 4) let Windows try to resolve it directly
        try:
            subprocess.Popen(f'start "" "{name}"', shell=True, creationflags=CREATE_NO_WINDOW)
            return f"Attempting to open {name}, sir."
        except Exception as e:
            return f"Couldn't open {name}, sir: {e}"

    def open_app(self, name):
        """Kept for backward compatibility — now just delegates to open_anything."""
        return self.open_anything(name)

    def open_vscode(self, path: str = None):
        """
        Opens VS Code, optionally at a specific file or folder.
        Requires the 'code' command to be on PATH (VS Code Command Palette
        -> 'Shell Command: Install code command in PATH').
        """
        try:
            cmd = ["code"]
            if path:
                cmd.append(path)
            subprocess.Popen(cmd, shell=True, creationflags=CREATE_NO_WINDOW)
            return f"Opening VS Code at {path}, sir." if path else "Opening VS Code, sir."
        except FileNotFoundError:
            return ("VS Code's 'code' command isn't on PATH, sir. Run "
                    "'Shell Command: Install code command in PATH' from the "
                    "Command Palette in VS Code, then try again.")
        except Exception as e:
            return f"Couldn't open VS Code, sir: {e}"

    def open_file_or_folder(self, path: str):
        """Explicit path-only opener — use when you already know it's a real path."""
        p = Path(path)
        if not p.exists():
            return f"I can't find {path}, sir."
        try:
            os.startfile(str(p))
            return f"Opening {p.name}, sir."
        except Exception as e:
            return f"Couldn't open {path}, sir: {e}"

    def close_app(self, name):
        subprocess.Popen(["taskkill", "/f", "/im", f"{name}.exe"], creationflags=CREATE_NO_WINDOW, capture_output=True)
        return f"Closed {name}, sir."

    def get_clipboard(self):
        r = subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", "Get-Clipboard"],
                          capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        return r.stdout.strip()

    def set_clipboard(self, text):
        # text goes in via stdin — quotes, newlines and unicode all
        # survive (the old -Value '...' broke on apostrophes)
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
             "-Command", "$input | Set-Clipboard"],
            input=str(text), text=True, encoding="utf-8",
            capture_output=True, creationflags=CREATE_NO_WINDOW)
        return "Copied to clipboard, sir."

    def list_processes(self):
        if not PSUTIL_OK: return "Not available, sir."
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent"]):
            try:
                if p.info["cpu_percent"] > 1:
                    procs.append(f"{p.info['name']}: {p.info['cpu_percent']:.1f}%")
            except: pass
        return "\n".join(procs[:10]) if procs else "No high CPU processes, sir."