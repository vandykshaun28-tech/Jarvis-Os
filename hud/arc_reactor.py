import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget


class ArcReactor(QWidget):

    def __init__(self):

        super().__init__()

        self.angle = 0

        self.pulse = 0

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.animate
        )

        self.timer.start(
            20
        )

        self.setMinimumSize(
            420,
            420
        )


    def animate(self):

        self.angle += 10

        self.pulse += 0.05

        self.update()


    def paintEvent(self, event):

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.Antialiasing
        )

        cx = self.width() / 2

        cy = self.height() / 2

        painter.translate(
            cx,
            cy
        )

        glow = int(
            180 +
            math.sin(
                self.pulse
            ) * 70
        )

        pen = QPen(
            QColor(
                0,
                212,
                255,
                glow
            )
        )

        pen.setWidth(
            4
        )

        painter.setPen(
            pen
        )

        painter.save()

        painter.rotate(
            self.angle
        )

        painter.drawEllipse(
            -150,
            -150,
            300,
            300
        )

        painter.drawEllipse(
            -110,
            -110,
            220,
            220
        )

        painter.restore()

        painter.save()

        painter.rotate(
            -self.angle * 0.7
        )

        painter.drawEllipse(
            -80,
            -80,
            160,
            160
        )

        painter.restore()

        painter.drawEllipse(
            -50,
            -50,
            100,
            100
        )

        core_glow = QColor(
            180,
            255,
            255,
            glow
        )

        painter.setBrush(
            core_glow
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.drawEllipse(
            -20,
            -20,
            40,
            40
        )