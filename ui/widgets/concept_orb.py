"""
concept_orb.py
──────────────
The concept-interface centrepiece, rebuilt natively in Qt:

  • deep-space backdrop with twinkling stars and faint nebulae
  • a breathing cloud of ~500 cyan particles orbiting the core
  • three thin arc rings rotating in alternating directions
  • a bright white-hot core with radial glow

States: idle (cyan, calm) / thinking (amber, faster) / speaking
(brighter pulse). Drop-in replacement for the old AICore widget —
same set_idle() / set_thinking() API.
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient
from PySide6.QtWidgets import QWidget


class ConceptOrb(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "idle"
        self.t = 0.0
        rng = random.Random(7)

        # orb particles
        self.pts = [{
            "a": rng.random() * math.pi * 2,
            "r": math.pow(rng.random(), 0.6),
            "ph": rng.random() * math.pi * 2,
            "sz": rng.random() * 1.8 + 0.5,
        } for _ in range(500)]

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(33)

    # ── public API (matches old AICore) ─────────
    def set_idle(self):     self.mode = "idle"
    def set_thinking(self): self.mode = "thinking"
    def set_speaking(self): self.mode = "speaking"

    def _tick(self):
        self.t += 0.016 if self.mode == "idle" else 0.034
        self.update()

    # ── paint ───────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        t = self.t

        # the global GridBackdrop paints the grid behind the whole app —
        # here we only pool a soft glow so the orb sits IN the grid
        cx, cy = W / 2, H / 2
        R = min(W, H) * 0.30
        g = QRadialGradient(cx, cy, R * 2.4)
        g.setColorAt(0, QColor(10, 30, 50, 190))
        g.setColorAt(1, QColor(8, 19, 36, 0))
        p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R * 2.4, R * 2.4)

        if self.mode == "thinking":
            pr, pg, pb = 245, 176, 65        # amber
        elif self.mode == "speaking":
            pr, pg, pb = 120, 235, 255       # bright ice
        else:
            pr, pg, pb = 60, 220, 250        # cyan

        # outer glow
        g = QRadialGradient(cx, cy, R * 1.7)
        g.setColorAt(0, QColor(pr, pg, pb, 34))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R * 1.7, R * 1.7)

        # rotating arc rings
        for k in range(3):
            radius = R * (1.12 + k * 0.16)
            direction = 1 if k % 2 else -1
            start = (t * 22 * direction + k * 47) % 360
            span = 300 - k * 40
            pen = QPen(QColor(pr, pg, pb, 60 - k * 15), 1.4)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawArc(int(cx - radius), int(cy - radius),
                      int(radius * 2), int(radius * 2),
                      int(start * 16), int(span * 16))

        # particle cloud
        p.setPen(Qt.NoPen)
        spin = t * (0.12 if self.mode == "idle" else 0.3)
        for pt in self.pts:
            wob = 1 + math.sin(t * 0.9 + pt["ph"]) * 0.06
            x = cx + math.cos(pt["a"] + spin) * pt["r"] * R * wob
            y = cy + math.sin(pt["a"] + spin) * pt["r"] * R * wob
            al = 0.25 + 0.55 * abs(math.sin(t + pt["ph"]))
            p.setBrush(QBrush(QColor(pr, pg, pb, int(al * 255))))
            p.drawEllipse(QPointF(x, y), pt["sz"], pt["sz"])

        # core
        pulse = 1 + math.sin(t * 2.2) * (0.05 if self.mode == "idle" else 0.16)
        core = QRadialGradient(cx, cy, R * 0.36 * pulse)
        core.setColorAt(0.0, QColor(240, 255, 255, 245))
        core.setColorAt(0.4, QColor(pr, pg, pb, 130))
        core.setColorAt(1.0, QColor(pr, pg, pb, 0))
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), R * 0.36 * pulse, R * 0.36 * pulse)

        p.end()
