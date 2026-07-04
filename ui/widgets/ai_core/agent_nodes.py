from math import cos, sin, radians

from PySide6.QtGui import (
    QColor,
    QFont,
    QRadialGradient,
    QPen,
)

from PySide6.QtCore import Qt, QRectF

from ui.widgets.ai_core.agent_registry import AgentRegistry


BADGE_RADIUS = 38


class AgentNodes:

    def __init__(self):

        self.registry = AgentRegistry()

    # --------------------------------------------------

    def draw(self, painter, center, animation):

        painter.save()

        icon_font = QFont()

        icon_font.setPointSize(17)

        label_font = QFont()

        label_font.setPointSize(9)

        label_font.setBold(True)

        for agent in self.registry.all():

            angle = radians(agent.angle)

            x = center.x() + cos(angle) * agent.radius

            y = center.y() + sin(angle) * agent.radius

            color = self._state_color(agent)

            # ---------------------------------
            # Outer glow
            # ---------------------------------

            glow = QRadialGradient(x, y, BADGE_RADIUS + 22)

            gc = QColor(color)

            gc.setAlpha(110)

            glow.setColorAt(0.0, gc)

            transparent = QColor(color)

            transparent.setAlpha(0)

            glow.setColorAt(1.0, transparent)

            painter.setPen(Qt.NoPen)

            painter.setBrush(glow)

            painter.drawEllipse(
                x - BADGE_RADIUS - 22,
                y - BADGE_RADIUS - 22,
                (BADGE_RADIUS + 22) * 2,
                (BADGE_RADIUS + 22) * 2,
            )

            # ---------------------------------
            # Badge fill
            # ---------------------------------

            painter.setBrush(QColor(6, 14, 22, 235))

            painter.drawEllipse(
                x - BADGE_RADIUS,
                y - BADGE_RADIUS,
                BADGE_RADIUS * 2,
                BADGE_RADIUS * 2,
            )

            # ---------------------------------
            # Badge ring
            # ---------------------------------

            pen = QPen(QColor(color))

            pen.setWidth(3)

            painter.setPen(pen)

            painter.setBrush(Qt.NoBrush)

            painter.drawEllipse(
                x - BADGE_RADIUS,
                y - BADGE_RADIUS,
                BADGE_RADIUS * 2,
                BADGE_RADIUS * 2,
            )

            # ---------------------------------
            # Icon
            # ---------------------------------

            painter.setFont(icon_font)

            painter.setPen(QColor(color))

            painter.drawText(
                QRectF(
                    x - BADGE_RADIUS,
                    y - BADGE_RADIUS,
                    BADGE_RADIUS * 2,
                    BADGE_RADIUS * 2,
                ),
                Qt.AlignCenter,
                agent.icon,
            )

            # ---------------------------------
            # Label pill
            # ---------------------------------

            painter.setFont(label_font)

            metrics = painter.fontMetrics()

            text = agent.name.upper()

            text_width = metrics.horizontalAdvance(text)

            pill_w = text_width + 26

            pill_h = 24

            pill_y = y + BADGE_RADIUS + 12

            painter.setPen(QPen(QColor(color)))

            painter.setBrush(QColor(6, 12, 18, 235))

            painter.drawRoundedRect(
                QRectF(
                    x - pill_w / 2,
                    pill_y,
                    pill_w,
                    pill_h,
                ),
                12,
                12,
            )

            painter.setPen(QColor("#ffffff"))

            painter.drawText(
                QRectF(
                    x - pill_w / 2,
                    pill_y,
                    pill_w,
                    pill_h,
                ),
                Qt.AlignCenter,
                text,
            )

        painter.restore()

    # --------------------------------------------------

    def _state_color(self, agent):

        if agent.state == "working":
            return "#00ff88"

        elif agent.state == "thinking":
            return "#bb66ff"

        elif agent.state == "speaking":
            return "#00d9ff"

        elif agent.state == "error":
            return "#ff4444"

        return agent.color
