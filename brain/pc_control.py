import os, subprocess, time
from pathlib import Path

try:
    import pyautogui
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

    def screenshot(self):
        if not PYGUI_OK: return "Not available, sir."
        d = Path(r"C:\jarvis_v18\memory\screenshots")
        d.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        p = str(d / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        pyautogui.screenshot().save(p)
        return f"Screenshot saved, sir."

    def type_text(self, text):
        if not PYGUI_OK: return "Not available, sir."
        time.sleep(0.5)
        pyautogui.typewrite(text, interval=0.05)
        return f"Typed: {text[:40]}"

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
        for root, dirs, files in os.walk(r"C:\Users\gameboks"):
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
        subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", f"Set-Clipboard -Value '{text}'"],
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