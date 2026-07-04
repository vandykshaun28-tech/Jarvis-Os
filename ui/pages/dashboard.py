from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
)

from ui.widgets.ai_core.ai_core import AICore


class DashboardPage(QWidget):

    def __init__(self):

        super().__init__()

        self.build_ui()

    def build_ui(self):

        root = QVBoxLayout()

        root.setContentsMargins(0, 0, 0, 0)

        root.setSpacing(0)

        self.setLayout(root)

        self.core = AICore()

        root.addWidget(self.core, 1)

        self.setStyleSheet("""

        QWidget{

            background:transparent;

        }

        """)
