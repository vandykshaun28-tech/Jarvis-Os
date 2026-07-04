from math import cos, sin, radians

from PySide6.QtGui import (
    QColor,
    QPen,
)

from PySide6.QtCore import Qt


class MolecularReactor:

    def __init__(self):

        self.count = 42

    def draw(self, painter, center, animation):

        painter.save()

        particles = []

        # -----------------------------
        # Outer rotating particles
        # -----------------------------

        for i in range(self.count):

            angle = radians(
                (360 / self.count) * i +
                animation.outer_angle * 3
            )

            radius = 22 + (i % 6) * 7

            x = center.x() + cos(angle) * radius

            y = center.y() + sin(angle) * radius

            particles.append((x, y))

        # -----------------------------
        # Connection lines
        # -----------------------------

        pen = QPen(
            QColor(70, 220, 255, 70),
            1,
        )

        painter.setPen(pen)

        for i in range(len(particles)):

            x1, y1 = particles[i]

            x2, y2 = particles[(i + 1) % len(particles)]

            painter.drawLine(
                int(x1),
                int(y1),
                int(x2),
                int(y2),
            )

        # -----------------------------
        # Particle nodes
        # -----------------------------

        painter.setPen(Qt.NoPen)

        for x, y in particles:

            painter.setBrush(
                QColor(110, 230, 255)
            )

            painter.drawEllipse(
                int(x) - 3,
                int(y) - 3,
                6,
                6,
            )

        # -----------------------------
        # Inner nucleus
        # -----------------------------

        painter.setBrush(
            QColor(90, 235, 255)
        )

        painter.drawEllipse(
            center,
            12,
            12,
        )

        painter.restore()