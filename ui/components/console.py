from PySide6.QtWidgets import (
    QWidget,
    QTextEdit,
    QVBoxLayout
)


class Console(QWidget):

    def __init__(self):

        super().__init__()

        self.setFixedWidth(360)

        layout = QVBoxLayout()

        self.setLayout(layout)

        self.console = QTextEdit()

        self.console.setReadOnly(True)

        self.console.setText(
            "JARVIS Console Online..."
        )

        layout.addWidget(self.console)

        self.setStyleSheet(
            """
            QWidget{

                background:#08111b;

                border:1px solid #10344d;

                border-radius:8px;

            }

            QTextEdit{

                background:#08111b;

                color:#00d9ff;

                border:none;

                font-family:Consolas;

            }
            """
        )