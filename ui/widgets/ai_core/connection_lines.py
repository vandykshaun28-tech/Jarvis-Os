from math import cos, sin, radians

from PySide6.QtGui import QColor, QPen
from PySide6.QtCore import Qt


class ConnectionLines:

    def __init__(self, nodes):

        self.nodes = nodes

    def draw(self, painter, center, animation):

        painter.save()

        pen = QPen(QColor(34, 211, 238, 90))
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)

        painter.setPen(pen)

        for agent in self.nodes.registry.all():

            angle = radians(agent.angle)

            x = center.x() + cos(angle) * agent.radius
            y = center.y() + sin(angle) * agent.radius

            # Stop the spoke short of the badge edge

            edge_x = center.x() + cos(angle) * (agent.radius - 40)
            edge_y = center.y() + sin(angle) * (agent.radius - 40)

            painter.drawLine(
                int(center.x()),
                int(center.y()),
                int(edge_x),
                int(edge_y),
            )

            # Relay dot roughly a third of the way out

            relay_r = agent.radius * 0.42

            rx = center.x() + cos(angle) * relay_r
            ry = center.y() + sin(angle) * relay_r

            painter.setPen(Qt.NoPen)

            painter.setBrush(QColor(34, 211, 238, 220))

            painter.drawEllipse(
                int(rx) - 5,
                int(ry) - 5,
                10,
                10,
            )

            painter.setBrush(QColor(6, 20, 30, 255))

            painter.drawEllipse(
                int(rx) - 2,
                int(ry) - 2,
                4,
                4,
            )

            painter.setPen(pen)

        painter.restore()
