from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
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

        self.setFixedHeight(96)

        self.build_ui()

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_status
        )

        self.timer.start(1000)

        self.update_status()

    def build_ui(self):

        layout = QHBoxLayout()

        layout.setContentsMargins(18, 10, 18, 10)

        layout.setSpacing(16)

        self.setLayout(layout)

        # ------------------------------------------------
        # Logo block
        # ------------------------------------------------

        self.logo = QLabel("\u2b21")

        self.logo.setFixedSize(56, 56)

        self.logo.setAlignment(Qt.AlignCenter)

        self.logo.setObjectName("logo")

        layout.addWidget(self.logo)

        title_block = QVBoxLayout()

        title_block.setSpacing(0)

        title_block.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel("JARVIS")

        self.title.setObjectName("title")

        self.subtitle = QLabel("AI COMMAND CENTER")

        self.subtitle.setObjectName("subtitle")

        title_block.addWidget(self.title)

        title_block.addWidget(self.subtitle)

        layout.addLayout(title_block)

        layout.addStretch()

        # ------------------------------------------------
        # Status pills
        # ------------------------------------------------

        self.cpu = StatusCard("CPU", icon="\u25a6", color="#22d3ee")

        self.ram = StatusCard("RAM", icon="\u25a4", color="#22d3ee")

        self.internet = StatusCard("Internet", icon="\U0001f310", color="#3b82f6")

        self.claude = StatusCard("Claude", icon="\U0001f9e0", color="#b06bff")

        self.voice = StatusCard("Voice", icon="\U0001f3a4", color="#14b8a6")

        self.memory = StatusCard("Memory", icon="\U0001f5c4", color="#22c55e")

        self.clock = StatusCard("Time", icon="\U0001f550", color="#7ba7c2")

        for card in (
            self.cpu,
            self.ram,
            self.internet,
            self.claude,
            self.voice,
            self.memory,
            self.clock,
        ):

            layout.addWidget(card)

        self.setStyleSheet("""

        QWidget{

            background:rgba(10,20,32,0.88);

            border:1px solid #12324a;

            border-radius:12px;

        }

        #logo{

            background:qradialgradient(
                cx:0.5, cy:0.5, radius:0.8,
                fx:0.5, fy:0.5,
                stop:0 #123049,
                stop:1 #05070d
            );

            border:2px solid #22d3ee;

            border-radius:28px;

            font-size:22px;

            color:#22d3ee;

        }

        #title{

            font-size:22px;

            font-weight:bold;

            color:white;

            border:none;

        }

        #subtitle{

            font-size:10px;

            font-weight:600;

            color:#5a8bb0;

            letter-spacing:2px;

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
