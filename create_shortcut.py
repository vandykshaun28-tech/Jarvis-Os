import os
import subprocess

desktop = r"C:\Users\gameboks\OneDrive\Desktop"

vbs_path = r"C:\jarvis_v18\make_shortcut.vbs"

vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
Set oLink = oWS.CreateShortcut("{desktop}\\JARVIS.lnk")
oLink.TargetPath = "pythonw.exe"
oLink.Arguments = "C:\\jarvis_v18\\main.py"
oLink.WorkingDirectory = "C:\\jarvis_v18"
oLink.Description = "JARVIS AI Command Centre"
oLink.Save'''

with open(vbs_path, "w") as f:
    f.write(vbs_content)

subprocess.run(["wscript", vbs_path])
os.remove(vbs_path)
print("JARVIS shortcut created on Desktop.")