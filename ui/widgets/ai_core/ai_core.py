from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter
from PySide6.QtCore import QPoint

from ui.widgets.ai_core.animation import AnimationEngine
from ui.widgets.ai_core.renderer import AICoreRenderer


class AICore(QWidget):

    def __init__(self):

        super().__init__()

        self.setMinimumSize(600, 420)

        self.animation = AnimationEngine(self)

        self.renderer = AICoreRenderer()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(
            self.width() // 2,
            self.height() // 2 - 30,
        )

        self.renderer.draw(
            painter,
            center,
            self.animation,
        )

        painter.end()