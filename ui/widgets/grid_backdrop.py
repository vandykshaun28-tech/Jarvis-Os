"""
grid_backdrop.py — the holographic grid painted across the ENTIRE
window, behind every panel. Deep navy, fine cyan gridlines, brighter
major lines, and slow-breathing HUD rings radiating from centre.
"""

import math

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient
from PySide6.QtWidgets import QWidget


class GridBackdrop(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.t = 0.0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(100)   # slow breathing — cheap on CPU

    def _tick(self):
        self.t += 0.05
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor("#081324"))

        minor, major = 40, 200
        pen_minor = QPen(QColor(34, 211, 238, 14), 1)
        pen_major = QPen(QColor(34, 211, 238, 32), 1)
        x = 0
        while x <= W:
            p.setPen(pen_major if x % major == 0 else pen_minor)
            p.drawLine(x, 0, x, H)
            x += minor
        y = 0
        while y <= H:
            p.setPen(pen_major if y % major == 0 else pen_minor)
            p.drawLine(0, y, W, y)
            y += minor

        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = W / 2, H / 2
        breath = 1 + math.sin(self.t) * 0.012
        for k in range(5):
            r = min(W, H) * (0.30 + k * 0.22) * breath
            p.setPen(QPen(QColor(34, 211, 238, 12), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)

        # gentle centre glow so the middle of the app feels lit
        g = QRadialGradient(cx, cy, min(W, H) * 0.55)
        g.setColorAt(0, QColor(20, 60, 90, 40))
        g.setColorAt(1, QColor(8, 19, 36, 0))
        p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), min(W, H) * 0.55, min(W, H) * 0.55)
        p.end()
