from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout
)

from PySide6.QtCore import Qt, QTimer
from datetime import datetime


class Header(QWidget):

    def __init__(self):

        super().__init__()

        self.build_ui()

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_clock
        )

        self.timer.start(1000)

        self.update_clock()


    def build_ui(self):

        layout = QHBoxLayout()

        layout.setContentsMargins(
            20,
            10,
            20,
            10
        )

        # Left

        left = QVBoxLayout()

        self.title = QLabel("JARVIS")

        self.title.setStyleSheet("""
            color:#00d8ff;
            font-size:28px;
            font-weight:bold;
        """)

        self.subtitle = QLabel(
            "AI OPERATING SYSTEM"
        )

        self.subtitle.setStyleSheet("""
            color:#5da8d6;
            font-size:11px;
        """)

        left.addWidget(self.title)

        left.addWidget(self.subtitle)

        layout.addLayout(left)

        layout.addStretch()

        # Status

        self.status = QLabel(
            "● Brain Online"
        )

        self.status.setStyleSheet("""
            color:#00ff88;
            font-size:14px;
        """)

        layout.addWidget(
            self.status
        )

        layout.addSpacing(30)

        self.clock = QLabel()

        self.clock.setStyleSheet("""
            color:#00d8ff;
            font-size:18px;
        """)

        layout.addWidget(
            self.clock
        )

        self.setLayout(
            layout
        )


    def update_clock(self):

        now = datetime.now()

        self.clock.setText(
            now.strftime(
                "%A  %d %B %Y   %H:%M:%S"
            )
        )