from math import cos, sin, radians

from PySide6.QtGui import QColor, QPen

from PySide6.QtCore import Qt


class Ring:

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

        self.outer = Ring(118, 28, 5, 3, "#00d9ff")

        self.middle = Ring(96, 22, 7, 2, "#33bbff")

        self.inner = Ring(74, 18, 9, 2, "#0099ff")

    def draw(self, painter, center, animation):

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