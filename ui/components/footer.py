from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout


class Footer(QWidget):

    def __init__(self):

        super().__init__()

        self.setFixedHeight(32)

        layout = QHBoxLayout()

        self.setLayout(layout)

        layout.addWidget(
            QLabel("JARVIS OS v20 • Ready")
        )

        layout.addStretch()

        self.setStyleSheet("""
        QWidget{
            background:#08111b;
            border:1px solid #10344d;
            border-radius:8px;
            color:#00d9ff;
            font-size:11px;
        }
        """)