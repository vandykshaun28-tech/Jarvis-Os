"""Simple 'coming soon' page for modules not built yet."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class PlaceholderPage(QWidget):

    def __init__(self, title, note="This module is under construction."):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setStyleSheet("color:#e8f6ff;font-size:22px;font-weight:700;border:none;")
        t.setAlignment(Qt.AlignCenter)
        n = QLabel(note)
        n.setStyleSheet("color:#5a8bb0;font-size:12px;border:none;")
        n.setAlignment(Qt.AlignCenter)
        lay.addStretch(); lay.addWidget(t); lay.addWidget(n); lay.addStretch()
