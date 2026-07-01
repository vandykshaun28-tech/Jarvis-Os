from math import sin

from PySide6.QtGui import (
    QColor,
    QRadialGradient,
)

from PySide6.QtCore import Qt


class Orb:

    def draw(self, painter, center, animation):

        pulse = 1 + (sin(animation.glow) * 0.08)

        r = int(55 * pulse)

        # Reactor Glow

        gradient = QRadialGradient(center, r + 45)

        gradient.setColorAt(0.0, QColor(140, 255, 255, 220))
        gradient.setColorAt(0.25, QColor(0, 217, 255, 180))
        gradient.setColorAt(0.70, QColor(0, 120, 255, 40))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)

        painter.setBrush(gradient)

        painter.drawEllipse(center, r + 45, r + 45)

        # Outer Shell

        painter.setBrush(QColor(10, 45, 70))

        painter.drawEllipse(center, r + 15, r + 15)

        # Inner Reactor

        painter.setBrush(QColor(45, 220, 255))

        painter.drawEllipse(center, r, r)

        # White Energy Core

        painter.setBrush(QColor(220, 255, 255, 180))

        painter.drawEllipse(center, 18, 18)