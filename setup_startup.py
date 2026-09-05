"""
setup_startup.py
────────────────
Make ALLISON open automatically when Windows starts — she is the
command centre, so she should be the first thing up.

Run once:   python setup_startup.py           (enable)
Undo:       python setup_startup.py --off      (disable)

It drops a small launcher into your Windows Startup folder that runs
Allison with the venv's windowless python (pythonw), so she boots
quietly with the machine. Single-instance lock in main_v20.py means
this never fights a copy you started by hand.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STARTUP = Path(os.environ.get("APPDATA", "")) / \
    "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LAUNCHER = STARTUP / "Allison.bat"

PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PY  = ROOT / ".venv" / "Scripts" / "python.exe"


def enable():
    if not STARTUP.exists():
        print(f"Startup folder not found: {STARTUP}")
        print("Are you on Windows? This only works there.")
        return
    py = PYW if PYW.exists() else PY
    bat = (
        "@echo off\r\n"
        f'cd /d "{ROOT}"\r\n'
        f'start "" "{py}" "{ROOT / "main_v20.py"}"\r\n'
    )
    LAUNCHER.write_text(bat, encoding="utf-8")
    print(f"[OK] Allison will now open on startup.\n     Launcher: {LAUNCHER}")
    print("     Reboot to test, or she'll open automatically next time "
          "you turn the PC on.")


def disable():
    if LAUNCHER.exists():
        LAUNCHER.unlink()
        print("[OK] Startup disabled — Allison no longer opens automatically.")
    else:
        print("Startup was not enabled (nothing to remove).")


if __name__ == "__main__":
    if "--off" in sys.argv or "--disable" in sys.argv:
        disable()
    else:
        enable()
