from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
)

from PySide6.QtCore import Qt


class StatusCard(QFrame):

    def __init__(self, title, value=""):

        super().__init__()

        self.setFixedSize(105, 60)

        layout = QVBoxLayout()

        layout.setContentsMargins(10, 8, 10, 8)

        layout.setSpacing(2)

        self.setLayout(layout)

        self.title = QLabel(title)

        self.title.setAlignment(Qt.AlignLeft)

        self.title.setObjectName("title")

        self.value = QLabel(value)

        self.value.setAlignment(Qt.AlignLeft)

        self.value.setObjectName("value")

        layout.addWidget(self.title)

        layout.addWidget(self.value)

        self.setStyleSheet("""

        QFrame{

            background:#071019;

            border:1px solid #123b5d;

            border-radius:8px;

        }

        QLabel{

            border:none;

        }

        #title{

            color:#7cbfdc;

            font-size:10px;

        }

        #value{

            color:white;

            font-size:18px;

            font-weight:bold;

        }

        """)