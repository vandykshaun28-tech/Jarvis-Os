from PySide6.QtWidgets import QWidget

from PySide6.QtGui import QPainter

from PySide6.QtCore import QPoint

from ui.widgets.ai_core.animation import AnimationEngine
from ui.widgets.ai_core.orb import Orb
from ui.widgets.ai_core.rings import Rings


class AICore(QWidget):

    def __init__(self):

        super().__init__()

        self.setMinimumSize(600, 420)

        self.animation = AnimationEngine(self)

        self.orb = Orb()

        self.rings = Rings()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(

            self.width() // 2,

            self.height() // 2 - 30

        )

        self.rings.draw(

            painter,

            center,

            self.animation

        )

        self.orb.draw(

            painter,

            center,

            self.animation

        )

        painter.end()