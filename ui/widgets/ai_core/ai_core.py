from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import QPoint, Qt

from ui.widgets.ai_core.animation import AnimationEngine
from ui.widgets.ai_core.renderer import AICoreRenderer


DESIGN_SIZE = 900.0


class AICore(QWidget):

    def __init__(self):

        super().__init__()

        self.setMinimumSize(500, 500)

        self.animation = AnimationEngine(self)

        self.renderer = AICoreRenderer()

    # --------------------------------------------------
    # State hooks (wired to the controller later)
    # --------------------------------------------------

    def set_idle(self):

        self.animation.speed = 0.30

    def set_thinking(self):

        self.animation.speed = 2.2

    def set_researching(self):

        self.animation.speed = 2.6

    def set_speaking(self):

        self.animation.speed = 1.1

    def set_memory(self):

        self.animation.speed = 0.85

    def set_error(self):

        self.animation.speed = 3.2

    # --------------------------------------------------

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()

        h = self.height()

        self._draw_background(painter, w, h)

        size = min(w, h)

        center_screen = QPoint(w // 2, h // 2)

        painter.save()

        painter.translate(center_screen)

        scale = size / DESIGN_SIZE

        painter.scale(scale, scale)

        design_center = QPoint(0, 0)

        self.renderer.draw(
            painter,
            design_center,
            self.animation,
        )

        painter.restore()

        painter.end()

    # --------------------------------------------------

    def _draw_background(self, painter, w, h):

        painter.fillRect(self.rect(), QColor("#05070d"))

        painter.setPen(Qt.NoPen)

        painter.setBrush(QColor(34, 211, 238, 20))

        for x in range(20, w, 46):

            for y in range(20, h, 46):

                painter.drawEllipse(x, y, 2, 2)
