import psutil
import platform
import socket
import getpass
import os

from PySide6.QtCore import QObject, Signal, QTimer


class SystemAgent(QObject):

    updated = Signal(dict)

    def __init__(self):

        super().__init__()

        self.state = {}

        self.timer = QTimer()

        self.timer.timeout.connect(self.update_state)

        self.timer.start(1000)

    # ----------------------------------------------------

    def update_state(self):

        try:

            self.state = {

                "cpu": psutil.cpu_percent(),

                "ram": psutil.virtual_memory().percent,

                "disk": psutil.disk_usage("/").percent,

                "boot_time": psutil.boot_time(),

                "username": getpass.getuser(),

                "hostname": socket.gethostname(),

                "platform": platform.system(),

                "platform_release": platform.release(),

                "python": platform.python_version(),

                "processes": len(psutil.pids()),

                "cwd": os.getcwd(),

            }

            self.updated.emit(self.state)

        except Exception as e:

            print("[SystemAgent]", e)