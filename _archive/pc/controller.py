import os
import subprocess
import webbrowser
import platform


class PCController:

    def open(self, target: str):

        target = target.strip()

        # Website
        if target.startswith("http"):
            webbrowser.open(target)
            return f"Opening {target}"

        # Folder or file
        if os.path.exists(target):
            os.startfile(target)
            return f"Opening {target}"

        # Windows application
        try:
            os.startfile(target)
            return f"Opening {target}"
        except Exception:
            pass

        # Try through shell

        try:
            subprocess.Popen(target, shell=True)
            return f"Launching {target}"
        except Exception as e:
            return str(e)

    def run(self, command):

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
        )

        return result.stdout

    def shutdown(self):

        subprocess.Popen("shutdown /s /t 0")

    def restart(self):

        subprocess.Popen("shutdown /r /t 0")

    def lock(self):

        if platform.system() == "Windows":
            subprocess.Popen(
                "rundll32.exe user32.dll,LockWorkStation"
            )