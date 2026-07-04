"""
JARVIS entry point.

Wrapped in a crash logger: when launched with pythonw.exe (no console,
as the desktop/startup shortcuts do) a startup failure would otherwise
be completely invisible. Any fatal error is written to
memory/crash.log and shown in a message box, so a dead shortcut always
leaves evidence.
"""

import os
import sys
import traceback
from datetime import datetime

# make imports work no matter where the shortcut launches us from
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)


def _already_running():
    """Single-instance lock — a second launch must never spawn a rival
    JARVIS that fights the first for the mic, camera and RAM."""
    import socket
    global _LOCK_SOCKET
    _LOCK_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _LOCK_SOCKET.bind(("127.0.0.1", 47821))
        return False
    except OSError:
        return True


def main():
    if _already_running():
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, "JARVIS is already running.\n\nLook for the orb icon in "
                   "the system tray (near the clock) and click it.",
                "JARVIS", 0x40)
        except Exception:
            print("JARVIS is already running.")
        sys.exit(0)

    from PySide6.QtWidgets import QApplication
    from ui.layouts.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        try:
            log = os.path.join(ROOT, "memory", "crash.log")
            os.makedirs(os.path.dirname(log), exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now().isoformat()} ===\n{err}\n")
        except Exception:
            pass
        # try to show the error even without a console
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "JARVIS failed to start.\n\n" + err[-800:] +
                "\n\nFull details in C:\\jarvis\\memory\\crash.log",
                "JARVIS crash", 0x10)
        except Exception:
            print(err)
        sys.exit(1)
