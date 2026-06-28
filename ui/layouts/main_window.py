from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame
)

from PySide6.QtCore import Qt
from ui.components.header import Header

class MainWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("JARVIS OS v20")

        self.resize(1700, 950)

        self.build_ui()

    def build_ui(self):

        root = QVBoxLayout()

        root.setContentsMargins(
            8,
            8,
            8,
            8
        )

        root.setSpacing(8)

        # =====================
        # Header
        # =====================

        self.header = Header()

                
        root.addWidget(
            self.header
        )

        # =====================
        # Middle Layout
        # =====================

        middle = QHBoxLayout()

        middle.setSpacing(8)

        # Sidebar

        self.sidebar = QFrame()

        self.sidebar.setFixedWidth(
            250
        )

        self.sidebar.setObjectName(
            "sidebar"
        )

        # Content

        self.content = QFrame()

        self.content.setObjectName(
            "content"
        )

        # Console

        self.console = QFrame()

        self.console.setFixedWidth(
            360
        )

        self.console.setObjectName(
            "console"
        )

        middle.addWidget(
            self.sidebar
        )

        middle.addWidget(
            self.content,
            1
        )

        middle.addWidget(
            self.console
        )

        root.addLayout(
            middle
        )

        # =====================
        # Footer
        # =====================

        self.footer = QFrame()

        self.footer.setFixedHeight(
            32
        )

        self.footer.setObjectName(
            "footer"
        )

        root.addWidget(
            self.footer
        )

        self.setStyleSheet(
            """
            QWidget{
                background:#05080d;
                color:#00d9ff;
                font-family:Segoe UI;
            }

            #header{
                background:#08111b;
                border:1px solid #10344d;
                border-radius:8px;
            }

            #sidebar{
                background:#08111b;
                border:1px solid #10344d;
                border-radius:8px;
            }

            #content{
                background:#08111b;
                border:1px solid #10344d;
                border-radius:8px;
            }

            #console{
                background:#08111b;
                border:1px solid #10344d;
                border-radius:8px;
            }

            #footer{
                background:#08111b;
                border:1px solid #10344d;
                border-radius:8px;
            }
            """
        )

        self.setLayout(
            root
        )