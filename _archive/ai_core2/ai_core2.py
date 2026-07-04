from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter
from PySide6.QtCore import QPoint

from ui.widgets.ai_core2.animation import AnimationEngine
from ui.widgets.ai_core2.renderer import AICore2Renderer


class AICore2(QWidget):

    def __init__(self):

        super().__init__()

        self.setMinimumSize(700, 700)

        self.animation = AnimationEngine(self)

        self.renderer = AICore2Renderer()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(
            self.width() // 2,
            self.height() // 2,
        )

        self.renderer.draw(
            painter,
            center,
            self.animation,
        )

        painter.end()