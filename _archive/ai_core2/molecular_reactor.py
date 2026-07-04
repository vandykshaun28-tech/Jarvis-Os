from math import sin, cos, radians

from PySide6.QtCore import Qt

from PySide6.QtGui import (
    QColor,
    QPen,
    QRadialGradient,
)


class MolecularReactor:

    def __init__(self):

        self.layers = 6

        self.particles = 18

    def draw(self, painter, center, animation):

        painter.save()

        # ==================================================
        # Background Glow
        # ==================================================

        glow = QRadialGradient(center, 140)

        glow.setColorAt(0.0, QColor(0, 220, 255, 120))
        glow.setColorAt(0.4, QColor(0, 160, 255, 40))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)

        painter.drawEllipse(center, 140, 140)

        # ==================================================
        # Molecular Bonds
        # ==================================================

        for layer in range(self.layers):

            radius = 22 + layer * 12

            points = []

            count = self.particles + layer * 4

            rotation = animation.outer_angle * (1.2 + layer * 0.25)

            for i in range(count):

                angle = radians(
                    (360 / count) * i + rotation
                )

                x = center.x() + cos(angle) * radius

                y = center.y() + sin(angle) * radius

                points.append((x, y))

            painter.setPen(

                QPen(

                    QColor(60, 200, 255, 40),

                    1,

                )

            )

            for i in range(len(points)):

                x1, y1 = points[i]

                x2, y2 = points[(i + 1) % len(points)]

                painter.drawLine(

                    int(x1),

                    int(y1),

                    int(x2),

                    int(y2),

                )

            painter.setPen(Qt.NoPen)

            for i, (x, y) in enumerate(points):

                pulse = 2 + abs(

                    sin(

                        animation.glow +

                        i * 0.35 +

                        layer

                    )

                ) * 4

                painter.setBrush(

                    QColor(

                        120,

                        235,

                        255,

                        210,

                    )

                )

                painter.drawEllipse(

                    int(x - pulse / 2),

                    int(y - pulse / 2),

                    int(pulse),

                    int(pulse),

                )

        # ==================================================
        # Reactor Core
        # ==================================================

        core = 34 + sin(animation.glow) * 4

        painter.setBrush(

            QColor(

                70,

                225,

                255,

            )

        )

        painter.drawEllipse(

            center,

            int(core),

            int(core),

        )

        painter.setBrush(

            QColor(

                225,

                255,

                255,

                210,

            )

        )

        painter.drawEllipse(

            center,

            12,

            12,

        )

        painter.restore()