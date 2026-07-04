from math import cos, sin, radians

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


class Packets:

    def __init__(self, nodes):

        self.nodes = nodes

    def draw(self, painter, center, animation):

        painter.save()

        painter.setPen(Qt.NoPen)

        progress = (animation.outer_angle % 360) / 360.0

        for agent in self.nodes.registry.all():

            angle = radians(agent.angle + animation.outer_angle)

            end_x = center.x() + cos(angle) * agent.radius
            end_y = center.y() + sin(angle) * agent.radius

            x = center.x() + (end_x - center.x()) * progress
            y = center.y() + (end_y - center.y()) * progress

            # Glow
            painter.setBrush(QColor(0, 220, 255, 60))
            painter.drawEllipse(
                int(x) - 5,
                int(y) - 5,
                10,
                10
            )

            # Core
            painter.setBrush(QColor("#00d9ff"))
            painter.drawEllipse(
                int(x) - 2,
                int(y) - 2,
                4,
                4
            )

        painter.restore()