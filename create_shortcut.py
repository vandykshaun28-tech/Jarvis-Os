"""
create_shortcut.py
──────────────────
Sets JARVIS up like an operating system feature:

  1. Desktop shortcut with the JARVIS orb icon
  2. Auto-start shortcut in the Windows Startup folder, so JARVIS
     boots with your laptop and is already listening in the background

Both launch through the project's own venv with pythonw.exe, so there
is no console window — just JARVIS.

Run once:  python create_shortcut.py
Undo auto-start any time: delete JARVIS.lnk from shell:startup
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main_v20.py"
ICON = ROOT / "assets" / "jarvis_orb.ico"

# prefer the venv's windowless python so no black console appears
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
if not PYW.exists():
    PYW = Path("pythonw.exe")   # fall back to whatever is on PATH

home = Path.home()
desktop = home / "OneDrive" / "Desktop"
if not desktop.exists():
    desktop = home / "Desktop"

startup = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) \
    / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

targets = [("Desktop", desktop / "JARVIS.lnk")]
if startup.exists():
    targets.append(("Startup (boots with Windows)", startup / "JARVIS.lnk"))

vbs_lines = ['Set oWS = WScript.CreateObject("WScript.Shell")']
for _, lnk in targets:
    vbs_lines += [
        f'Set oLink = oWS.CreateShortcut("{lnk}")',
        f'oLink.TargetPath = "{PYW}"',
        f'oLink.Arguments = """{MAIN}"""',
        f'oLink.WorkingDirectory = "{ROOT}"',
        f'oLink.IconLocation = "{ICON}"',
        'oLink.Description = "JARVIS — AI Command Centre"',
        'oLink.Save',
    ]

vbs_path = ROOT / "make_shortcut.vbs"
vbs_path.write_text("\r\n".join(vbs_lines), encoding="utf-8")
subprocess.run(["cscript", "//nologo", str(vbs_path)], check=True)
vbs_path.unlink(missing_ok=True)

for label, lnk in targets:
    print(f"  created: {label} -> {lnk}")
print("\nDone. JARVIS will start automatically at your next login.")
print("Tip: he speaks and listens from boot — say 'hey jarvis' any time.")
