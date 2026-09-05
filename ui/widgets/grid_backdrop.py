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
        self.light = False   # theme flag — set via set_theme()
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(100)   # slow breathing — cheap on CPU

    def set_theme(self, name: str):
        self.light = (name == "light")
        self.update()

    def _tick(self):
        self.t += 0.05
        self.update()

    def paintEvent(self, event):
        from ui.styles.theme_manager import pal
        p = QPainter(self)
        W, H = self.width(), self.height()
        theme = pal()
        base = QColor(theme["canvas"])
        grid = theme["grid"]
        try:
            ah = theme.get("accent", "#3dd8ff").lstrip("#")
            ar, ag, ab = (int(ah[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            ar, ag, ab = (61, 216, 255)
        p.fillRect(0, 0, W, H, base)

        # ── fine, subtle grid (JARVIS-style: dark, tight, low-contrast) ──
        minor, major = 34, 170
        pen_minor = QPen(QColor(*grid, 8), 1)
        pen_major = QPen(QColor(*grid, 16), 1)
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

        # ── faint top-edge tick ruler (a HUD detail from his look) ──
        tick_pen = QPen(QColor(ar, ag, ab, 45), 1)
        long_pen = QPen(QColor(ar, ag, ab, 80), 1)
        tx = 0
        i = 0
        while tx <= W:
            longt = (i % 5 == 0)
            p.setPen(long_pen if longt else tick_pen)
            p.drawLine(tx, 0, tx, 9 if longt else 5)
            tx += 22
            i += 1

        # ── one or two very faint breathing rings from centre ──
        cx, cy = W / 2, H / 2
        breath = 1 + math.sin(self.t) * 0.012
        for k in range(2):
            r = min(W, H) * (0.42 + k * 0.30) * breath
            p.setPen(QPen(QColor(ar, ag, ab, 9), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)

        # gentle centre glow so the middle of the app feels lit
        g = QRadialGradient(cx, cy, min(W, H) * 0.55)
        g.setColorAt(0, QColor(ar, ag, ab, 26))
        g.setColorAt(1, QColor(*base.getRgb()[:3], 0))
        p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), min(W, H) * 0.55, min(W, H) * 0.55)
        p.end()
