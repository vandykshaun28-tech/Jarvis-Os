from PySide6.QtWidgets import QApplication
import sys

from hud.hud import JarvisHUD

app = QApplication(sys.argv)

window = JarvisHUD()

window.show()

sys.exit(
    app.exec()
)