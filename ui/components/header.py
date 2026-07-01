from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
)

from PySide6.QtCore import (
    Qt,
    QTimer,
)

from datetime import datetime

import psutil

from ui.widgets.ai_core.status_card import StatusCard


class Header(QWidget):

    def __init__(self):

        super().__init__()

        self.setFixedHeight(78)

        self.build_ui()

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_status
        )

        self.timer.start(1000)

        self.update_status()

    def build_ui(self):

        layout = QHBoxLayout()

        layout.setContentsMargins(
            20,
            8,
            20,
            8
        )

        layout.setSpacing(12)

        self.setLayout(layout)

        # ------------------------

        self.title = QLabel(
            "JARVIS AI COMMAND CENTER"
        )

        self.title.setObjectName(
            "title"
        )

        layout.addWidget(self.title)

        layout.addStretch()

        # ------------------------

        self.cpu = StatusCard(
            "CPU"
        )

        self.ram = StatusCard(
            "RAM"
        )

        self.internet = StatusCard(
            "Internet"
        )

        self.claude = StatusCard(
            "Claude"
        )

        self.voice = StatusCard(
            "Voice"
        )

        self.memory = StatusCard(
            "Memory"
        )

        self.clock = StatusCard(
            "Time"
        )

        layout.addWidget(
            self.cpu
        )

        layout.addWidget(
            self.ram
        )

        layout.addWidget(
            self.internet
        )

        layout.addWidget(
            self.claude
        )

        layout.addWidget(
            self.voice
        )

        layout.addWidget(
            self.memory
        )

        layout.addWidget(
            self.clock
        )

        self.setStyleSheet("""

        QWidget{

            background:#071019;

            border:1px solid #123b5d;

            border-radius:8px;

            color:#00d9ff;

        }

        #title{

            font-size:22px;

            font-weight:bold;

            color:white;

            border:none;

        }

        """)

    def update_status(self):

        cpu = psutil.cpu_percent()

        ram = psutil.virtual_memory().percent

        self.cpu.value.setText(
            f"{cpu:.0f}%"
        )

        self.ram.value.setText(
            f"{ram:.0f}%"
        )

        self.internet.value.setText(
            "Online"
        )

        self.claude.value.setText(
            "Ready"
        )

        self.voice.value.setText(
            "Ready"
        )

        self.memory.value.setText(
            "Active"
        )

        self.clock.value.setText(

            datetime.now().strftime(

                "%H:%M:%S"

            )

        )