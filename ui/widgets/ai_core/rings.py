from math import cos, sin, radians

from PySide6.QtGui import (
    QColor,
    QPen,
)

from PySide6.QtCore import Qt


class Ring:

    def __init__(
        self,
        radius,
        segments,
        length,
        thickness,
        color,
    ):
        self.radius = radius
        self.segments = segments
        self.length = length
        self.thickness = thickness
        self.color = QColor(color)

    def draw(self, painter, center, angle):

        painter.save()

        painter.translate(center)

        painter.rotate(angle)

        pen = QPen(self.color)
        pen.setWidth(self.thickness)
        pen.setCapStyle(Qt.RoundCap)

        painter.setPen(pen)

        step = 360 / self.segments

        for i in range(self.segments):

            a1 = radians(i * step)
            a2 = radians(i * step + self.length)

            x1 = cos(a1) * self.radius
            y1 = sin(a1) * self.radius

            x2 = cos(a2) * self.radius
            y2 = sin(a2) * self.radius

            painter.drawLine(
                int(x1),
                int(y1),
                int(x2),
                int(y2),
            )

        painter.restore()


class Rings:

    def __init__(self):

        self.outer = Ring(
            radius=108,
            segments=24,
            length=6,
            thickness=3,
            color="#00d9ff",
        )

        self.inner = Ring(
            radius=82,
            segments=18,
            length=8,
            thickness=2,
            color="#0099ff",
        )

    def draw(self, painter, center, animation):

        self.outer.draw(
            painter,
            center,
            animation.outer_angle,
        )

        self.inner.draw(
            painter,
            center,
            animation.inner_angle,
        )

        #
        # Radar Sweep
        #

        painter.save()

        painter.translate(center)

        painter.rotate(animation.outer_angle * 2)

        sweep = QPen(QColor(120, 255, 255))

        sweep.setWidth(5)

        sweep.setCapStyle(Qt.RoundCap)

        painter.setPen(sweep)

        painter.drawLine(0, 0, 125, 0)

        painter.restore()