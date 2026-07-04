from math import sin, cos, radians, sqrt, pi

from PySide6.QtGui import (
    QColor,
    QRadialGradient,
    QPen,
)

from PySide6.QtCore import Qt


def _fibonacci_sphere(count):

    points = []

    golden_angle = pi * (3.0 - sqrt(5.0))

    for i in range(count):

        y = 1 - (i / float(count - 1)) * 2

        radius_at_y = sqrt(max(0.0, 1 - y * y))

        theta = golden_angle * i

        x = cos(theta) * radius_at_y

        z = sin(theta) * radius_at_y

        points.append((x, y, z))

    return points


class Orb:
    """Molecular / neural network reactor core."""

    NODE_COUNT = 34

    def __init__(self):

        self.points = _fibonacci_sphere(self.NODE_COUNT)

        # Precompute a set of short-range edges (nearest neighbours)

        self.edges = self._build_edges(self.points)

    # --------------------------------------------------

    def _build_edges(self, points):

        edges = []

        for i, p in enumerate(points):

            distances = []

            for j, q in enumerate(points):

                if i == j:

                    continue

                d = (
                    (p[0] - q[0]) ** 2 +
                    (p[1] - q[1]) ** 2 +
                    (p[2] - q[2]) ** 2
                )

                distances.append((d, j))

            distances.sort()

            for _, j in distances[:2]:

                pair = tuple(sorted((i, j)))

                if pair not in edges:

                    edges.append(pair)

        return edges

    # --------------------------------------------------

    def draw(self, painter, center, animation):

        painter.save()

        core_radius = 118

        pulse = 1 + (sin(animation.glow) * 0.05)

        r = core_radius * pulse

        # -----------------------------------------
        # Outer ambient glow (blue -> purple)
        # -----------------------------------------

        glow = QRadialGradient(center, r + 70)

        glow.setColorAt(0.0, QColor(120, 210, 255, 130))
        glow.setColorAt(0.35, QColor(120, 100, 255, 70))
        glow.setColorAt(0.75, QColor(60, 40, 160, 25))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.NoPen)

        painter.setBrush(glow)

        painter.drawEllipse(center, r + 70, r + 70)

        # -----------------------------------------
        # Rotate the node cloud slowly
        # -----------------------------------------

        angle = radians(animation.middle_angle)

        cos_a = cos(angle)

        sin_a = sin(angle)

        projected = []

        for (x, y, z) in self.points:

            # Rotate around Y axis

            rx = x * cos_a - z * sin_a

            rz = x * sin_a + z * cos_a

            ry = y

            screen_x = center.x() + rx * r

            screen_y = center.y() + ry * r * 0.92

            depth = (rz + 1) / 2.0

            projected.append((screen_x, screen_y, depth))

        # -----------------------------------------
        # Edges (network lines)
        # -----------------------------------------

        for i, j in self.edges:

            x1, y1, d1 = projected[i]

            x2, y2, d2 = projected[j]

            avg_depth = (d1 + d2) / 2.0

            alpha = int(30 + avg_depth * 90)

            pen = QPen(QColor(140, 170, 255, alpha))

            pen.setWidthF(1.0)

            painter.setPen(pen)

            painter.drawLine(
                int(x1), int(y1),
                int(x2), int(y2),
            )

        # -----------------------------------------
        # Nodes
        # -----------------------------------------

        painter.setPen(Qt.NoPen)

        for idx, (x, y, depth) in enumerate(projected):

            size = 4 + depth * 7

            if idx % 5 == 0:

                color = QColor(190, 140, 255, int(140 + depth * 100))

            else:

                color = QColor(110, 200, 255, int(140 + depth * 100))

            painter.setBrush(color)

            painter.drawEllipse(
                x - size / 2,
                y - size / 2,
                size,
                size,
            )

        # -----------------------------------------
        # Bright nucleus
        # -----------------------------------------

        nucleus = QRadialGradient(center, 22)

        nucleus.setColorAt(0.0, QColor(255, 255, 255, 235))
        nucleus.setColorAt(0.5, QColor(150, 210, 255, 200))
        nucleus.setColorAt(1.0, QColor(120, 160, 255, 0))

        painter.setBrush(nucleus)

        painter.drawEllipse(center, 22, 22)

        painter.restore()
