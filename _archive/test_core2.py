import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from ui.widgets.ai_core2.ai_core2 import AICore2


class TestWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("JARVIS AI Core 2")

        self.resize(1000, 1000)

        self.setCentralWidget(
            AICore2()
        )


app = QApplication(sys.argv)

window = TestWindow()

window.show()

sys.exit(app.exec())