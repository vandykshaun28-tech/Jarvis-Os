"""
create_shortcut.py
──────────────────
Creates a desktop shortcut that launches JARVIS (main_v20.py).
Paths are derived from wherever this project folder lives — no
hardcoded locations.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main_v20.py"

# OneDrive-redirected desktops are common; prefer it if it exists.
home = Path.home()
desktop = home / "OneDrive" / "Desktop"
if not desktop.exists():
    desktop = home / "Desktop"

vbs_path = ROOT / "make_shortcut.vbs"

vbs = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{desktop}\\JARVIS.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "pythonw.exe"
oLink.Arguments = """{MAIN}"""
oLink.WorkingDirectory = "{ROOT}"
oLink.Description = "JARVIS AI Command Centre"
oLink.Save
'''

vbs_path.write_text(vbs, encoding="utf-8")
subprocess.run(["cscript", "//nologo", str(vbs_path)], check=True)
vbs_path.unlink(missing_ok=True)
print(f"Shortcut created on {desktop}")
