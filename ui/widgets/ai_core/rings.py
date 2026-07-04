from math import cos, sin, radians

from PySide6.QtGui import QColor, QPen

from PySide6.QtCore import Qt


class DashedRing:
    """A single rotating, segmented ring (subtle motion accent)."""

    def __init__(self, radius, segments, length, width, color):

        self.radius = radius
        self.segments = segments
        self.length = length
        self.width = width
        self.color = QColor(color)

    def draw(self, painter, center, rotation):

        painter.save()

        painter.translate(center)

        painter.rotate(rotation)

        pen = QPen(self.color)

        pen.setWidth(self.width)

        pen.setCapStyle(Qt.RoundCap)

        painter.setPen(pen)

        step = 360 / self.segments

        for i in range(self.segments):

            a1 = radians(i * step)

            a2 = radians(i * step + self.length)

            painter.drawLine(

                int(cos(a1) * self.radius),
                int(sin(a1) * self.radius),

                int(cos(a2) * self.radius),
                int(sin(a2) * self.radius)

            )

        painter.restore()


class Rings:

    def __init__(self):

        # Many faint concentric static circles, like the concept image

        self.static_radii = [
            60, 105, 150, 195, 240, 285, 330, 375, 420,
        ]

        # A couple of rotating segmented rings for subtle motion

        self.outer = DashedRing(420, 42, 4, 2, "#22d3ee")

        self.middle = DashedRing(330, 34, 5, 2, "#22d3ee")

        self.inner = DashedRing(240, 26, 6, 2, "#22d3ee")

    def draw(self, painter, center, animation):

        painter.save()

        painter.setBrush(Qt.NoBrush)

        for i, radius in enumerate(self.static_radii):

            alpha = 34 if i % 3 != 0 else 60

            pen = QPen(QColor(34, 211, 238, alpha))

            pen.setWidth(1)

            painter.setPen(pen)

            painter.drawEllipse(
                center,
                radius,
                radius,
            )

        painter.restore()

        self.outer.draw(
            painter,
            center,
            animation.outer_angle
        )

        self.middle.draw(
            painter,
            center,
            animation.middle_angle
        )

        self.inner.draw(
            painter,
            center,
            animation.inner_angle
        )
