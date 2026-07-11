"""
concept_orb.py — the holographic neural brain.
──────────────────────────────────────────────
A glowing 3-D neural-network brain: crisp particle surface, synapse
lines between nearby neurons, bright hub nodes, and — when JARVIS is
thinking or working — visible PULSES firing along the synapses.
Beneath it floats a holographic projector platform with rotating
rings and a stream of data particles raining from the brain into it.
Colourful ambient nodes (magenta / violet / green / gold) drift
around the brain like the concept art.

A status readout under the platform always tells you what he's doing:
    ● STANDING BY          (idle — dim, slow)
    ◉ THINKING…            (amber, sparks firing, spinner arc)
    ⚙ WORKING — <detail>   (orange, heavy synapse fire)
    ▶ SPEAKING             (cyan pulse)

Drag to spin. Double-click to resume auto-rotation.
API: set_idle() / set_thinking() / set_speaking() / set_working(detail)
     / set_compact(bool)   — superset of the old orb, drop-in safe.
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                           QRadialGradient, QLinearGradient)
from PySide6.QtWidgets import QWidget


def _accent_rgb():
    try:
        from ui.styles.theme_manager import pal
        hexc = pal().get("accent", "#22d3ee").lstrip("#")
        return tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (34, 211, 238)


def _brain_points(n, rng):
    """n (x,y,z) points on a brain-shaped surface."""
    pts = []
    attempts = 0
    while len(pts) < n and attempts < n * 40:
        attempts += 1
        u = rng.uniform(0, math.pi * 2)
        v = math.acos(rng.uniform(-1, 1))
        sx = math.sin(v) * math.cos(u)
        sy = math.sin(v) * math.sin(u)
        sz = math.cos(v)
        x = sx * 1.15
        y = sy * 0.82
        z = sz * 1.35
        if y < 0:
            y *= 0.72
        # central fissure gap
        if abs(x) < 0.09 and y > -0.1:
            if rng.random() < 0.85:
                continue
        # folds
        fold = (0.05 * math.sin(6.0 * u + 3.0 * v)
                + 0.045 * math.sin(9.0 * v)
                + 0.035 * math.sin(7.0 * u))
        s = 1.0 + fold
        x *= s; y *= s; z *= s
        if z > 0.6:
            y += 0.05
        pts.append([x, y, z])
    while len(pts) < n:
        pts.append([rng.uniform(-1, 1) * 1.1,
                    rng.uniform(-1, 1) * 0.8,
                    rng.uniform(-1, 1) * 1.3])
    return pts


def _build_synapses(pts, hub_idx, per_hub, rng):
    """Edges between each hub and its nearest hub neighbours (3-D)."""
    edges = set()
    for i in hub_idx:
        p = pts[i]
        near = []
        for j in hub_idx:
            if i == j:
                continue
            q = pts[j]
            d = ((p[0]-q[0])**2 + (p[1]-q[1])**2 + (p[2]-q[2])**2)
            near.append((d, j))
        near.sort()
        for _, j in near[:per_hub]:
            if rng.random() < 0.9:
                edges.add(tuple(sorted((i, j))))
    return list(edges)


# ambient constellation colours (the concept art's coloured dots)
STAR_COLOURS = [(255, 70, 220), (160, 90, 255), (70, 255, 160),
                (255, 190, 70), (90, 160, 255)]


class ConceptOrb(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "idle"
        self.detail = ""
        self.t = 0.0
        self._energy = 0.0
        self.compact = False
        self._scale_now = 1.0

        rng = random.Random(23)
        self.pts = _brain_points(1250, rng)
        self.phase = [rng.random() * math.pi * 2 for _ in self.pts]

        # hubs = brighter neurons; synapses connect them
        self.hubs = list(range(0, len(self.pts), 5))
        self.edges = _build_synapses(self.pts, self.hubs, 2, rng)

        # firing pulses travelling along synapses: [edge, t, speed]
        self._sparks = []
        self._rng = rng

        # ── memory dots ──────────────────────────────────────────────
        # every permanent memory JARVIS forms lights ONE neuron gold,
        # in a fixed scattered order — the brain literally fills with
        # what he has learned. Newly formed memories flash as they land.
        mem_rng = random.Random(7)
        self._mem_order = list(range(len(self.pts)))
        mem_rng.shuffle(self._mem_order)
        self._mem_count = 0
        self._mem_set = set()
        self._mem_flash = {}          # point index -> t when it was lit

        # ambient coloured stars orbiting the brain
        self.stars = []
        for k in range(26):
            self.stars.append({
                "r": rng.uniform(1.55, 2.25),
                "th": rng.uniform(0, math.pi * 2),      # orbit angle
                "y": rng.uniform(-0.9, 1.0),
                "spd": rng.uniform(0.001, 0.004) * rng.choice((1, -1)),
                "col": STAR_COLOURS[k % len(STAR_COLOURS)],
                "ph": rng.random() * math.pi * 2,
            })

        # data-stream particles raining into the platform
        self.rain = [{"p": rng.random(), "x": rng.uniform(-1, 1),
                      "spd": rng.uniform(0.004, 0.011)} for _ in range(46)]

        self.yaw = 0.5
        self.pitch = -0.15
        self._drag = None
        self._auto = True
        self.setCursor(Qt.OpenHandCursor)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(33)

    # ── public state API (superset of the old orb) ──────────────────
    def set_idle(self):
        self.mode = "idle"; self.detail = ""

    def set_thinking(self):
        self.mode = "thinking"; self.detail = ""

    def set_speaking(self):
        self.mode = "speaking"; self.detail = ""

    def set_working(self, detail=""):
        self.mode = "working"; self.detail = str(detail)[:60]

    def set_compact(self, on: bool):
        self.compact = bool(on)

    def set_memory_count(self, n: int):
        """Light up n gold neurons — one per permanent memory/studied
        topic. New ones flash white→gold as the memory forms."""
        n = max(0, min(int(n), len(self._mem_order)))
        if n == self._mem_count:
            return
        if n > self._mem_count:
            for idx in self._mem_order[self._mem_count:n]:
                self._mem_flash[idx] = self.t
        self._mem_count = n
        self._mem_set = set(self._mem_order[:n])

    # ── animation clock ──────────────────────────────────────────────
    def _tick(self):
        target = {"thinking": 1.0, "working": 1.0, "speaking": 0.55}\
            .get(self.mode, 0.12)
        self._energy += (target - self._energy) * 0.07
        e = self._energy
        self.t += 0.016 + e * 0.02
        if self._auto:
            self.yaw += 0.0035 + e * 0.004

        # spawn synapse pulses — a trickle when idle, a storm when busy
        rate = 0.04 + e * 0.55
        if self._rng.random() < rate and len(self._sparks) < 40:
            self._sparks.append([self._rng.randrange(len(self.edges)),
                                 0.0, self._rng.uniform(0.03, 0.07)])
        for s in self._sparks:
            s[1] += s[2] * (1.0 + e)
        self._sparks = [s for s in self._sparks if s[1] < 1.0]

        for st in self.stars:
            st["th"] += st["spd"] * (1 + e * 1.5)
        for r in self.rain:
            r["p"] += r["spd"] * (0.6 + e)
            if r["p"] > 1.0:
                r["p"] = 0.0
                r["x"] = self._rng.uniform(-1, 1)

        tgt = 0.5 if self.compact else 1.0
        self._scale_now += (tgt - self._scale_now) * 0.12
        self.update()

    # ── mouse: drag to spin ──────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.position().toPoint()
            self._auto = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            pos = event.position().toPoint()
            self.yaw += (pos.x() - self._drag.x()) * 0.01
            self.pitch += (pos.y() - self._drag.y()) * 0.01
            self.pitch = max(-1.4, min(1.4, self.pitch))
            self._drag = pos

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self._auto = True

    # ── painting ─────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        t, e = self.t, self._energy

        if self.compact:
            cx = W / 2 + (W * 0.30) * (1 - self._scale_now)
            cy = H / 2 - (H * 0.26) * (1 - self._scale_now)
        else:
            cx, cy = W / 2, H / 2 - min(W, H) * 0.05
        R = min(W, H) * 0.30 * self._scale_now

        r0, g0, b0 = _accent_rgb()
        # busy = warm shift toward electric white-blue
        rr0 = int(r0 + (120 - r0) * 0)  # base stays accent
        plat_y = cy + R * 1.42

        # ambient pool behind the brain
        pool = QRadialGradient(cx, cy, R * 1.8)
        pool.setColorAt(0, QColor(r0, g0, b0, int(26 + 34 * e)))
        pool.setColorAt(1, QColor(8, 19, 36, 0))
        p.setBrush(QBrush(pool)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R * 1.8, R * 1.8)

        # ── holographic platform (draw first — everything floats above)
        self._draw_platform(p, cx, plat_y, R, t, e, (r0, g0, b0))

        # ── light beam + data rain between brain and platform
        self._draw_beam(p, cx, cy, plat_y, R, e, (r0, g0, b0))

        # ── project the brain ────────────────────────────────────────
        cyaw, syaw = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)

        def project(x, y, z):
            x1 = x * cyaw + z * syaw
            z1 = -x * syaw + z * cyaw
            y2 = y * cp - z1 * sp
            z2 = y * sp + z1 * cp
            f = 1.7 / (z2 + 2.6)
            return cx + x1 * R * f, cy - y2 * R * f, z2

        proj = [project(x, y, z) for (x, y, z) in self.pts]

        # think-wave sweeping front→back (colour only, keeps outline crisp)
        wave = math.sin(t * 1.5) * 1.35

        # synapse lines (behind the dots)
        for (i, j) in self.edges:
            x1, y1, z1 = proj[i]
            x2, y2, z2 = proj[j]
            d = max(0.15, min(1.0, ((z1 + z2) / 2 + 1.4) / 2.8))
            a = int((26 + 60 * d) * (0.75 + 0.5 * e))
            pen = QPen(QColor(r0, g0, b0, min(a, 120)))
            pen.setWidthF(0.8 + 0.5 * d)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # neurons — small crisp dots, hubs brighter, MEMORIES gold
        p.setPen(Qt.NoPen)
        hubset = set(self.hubs)
        # retire finished memory flashes (~3s each)
        if self._mem_flash:
            self._mem_flash = {k: b for k, b in self._mem_flash.items()
                               if t - b < 3.0}
        order = sorted(range(len(proj)), key=lambda k: proj[k][2])
        for k in order:
            px, py, z2 = proj[k]
            dfront = max(0.2, min(1.0, (z2 + 1.4) / 2.8))
            tw = 0.7 + 0.3 * math.sin(t * 1.2 + self.phase[k])

            if k in self._mem_set:
                # a formed memory — warm gold, always gently alive
                glow = 0.75 + 0.25 * math.sin(t * 1.6 + self.phase[k])
                cr, cg, cb = 255, 200, 90
                sz = 1.9 + 1.1 * dfront
                alpha = int((150 + 105 * dfront) * glow)
                birth = self._mem_flash.get(k)
                if birth is not None:
                    # newborn memory: white flash + expanding halo ring
                    age = (t - birth) / 3.0
                    mix = max(0.0, 1.0 - age)
                    cr = int(255)
                    cg = int(200 + 55 * mix)
                    cb = int(90 + 165 * mix)
                    alpha = min(255, int(alpha + 90 * mix))
                    ring_r = sz + age * 16
                    pen = QPen(QColor(255, 220, 130, int(170 * mix)))
                    pen.setWidthF(1.3)
                    p.setPen(pen); p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(px, py), ring_r, ring_r)
                    p.setPen(Qt.NoPen)
                p.setBrush(QBrush(QColor(cr, cg, cb, alpha)))
                p.drawEllipse(QPointF(px, py), sz, sz)
                continue

            wave_hit = max(0, 1 - abs(self.pts[k][2] - wave) * 3.0) * e
            cr = int(r0 + (255 - r0) * wave_hit)
            cg = int(g0 + (255 - g0) * wave_hit)
            cb = int(b0 + (255 - b0) * wave_hit)
            if k in hubset:
                sz = 1.7 + 1.0 * dfront
                alpha = int(120 + 135 * dfront * tw)
            else:
                sz = 1.0 + 0.6 * dfront
                alpha = int(85 + 150 * dfront * tw)
            p.setBrush(QBrush(QColor(cr, cg, cb, alpha)))
            p.drawEllipse(QPointF(px, py), sz, sz)

        # firing pulses along synapses — the visible "he is thinking"
        for edge_i, ft, _ in self._sparks:
            i, j = self.edges[edge_i]
            x1, y1, z1 = proj[i]
            x2, y2, z2 = proj[j]
            px = x1 + (x2 - x1) * ft
            py = y1 + (y2 - y1) * ft
            d = max(0.2, min(1.0, ((z1 + z2) / 2 + 1.4) / 2.8))
            glow = QRadialGradient(px, py, 7)
            glow.setColorAt(0, QColor(255, 255, 255, int(220 * d)))
            glow.setColorAt(0.4, QColor(r0, g0, b0, int(160 * d)))
            glow.setColorAt(1, QColor(r0, g0, b0, 0))
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(px, py), 7, 7)

        # ambient coloured constellation
        for st in self.stars:
            sx = math.cos(st["th"]) * st["r"]
            sz = math.sin(st["th"]) * st["r"]
            px, py, z2 = project(sx, st["y"], sz)
            d = max(0.25, min(1.0, (z2 + 1.6) / 3.2))
            twk = 0.55 + 0.45 * math.sin(t * 2.0 + st["ph"])
            cr, cg, cb = st["col"]
            p.setBrush(QBrush(QColor(cr, cg, cb, int(150 * d * twk))))
            p.drawEllipse(QPointF(px, py), 1.6 + 1.6 * d * twk,
                          1.6 + 1.6 * d * twk)

        # spinner arc while thinking/working — unmistakable "busy" cue
        if e > 0.25 and self.mode in ("thinking", "working"):
            pen = QPen(QColor(255, 200, 90, int(190 * min(1, e))))
            pen.setWidthF(2.2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            arc_r = R * 1.28
            rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
            start = int((-t * 240) % 360) * 16
            p.drawArc(rect, start, 70 * 16)
            p.drawArc(rect, start + 180 * 16, 70 * 16)

        # ── status readout ───────────────────────────────────────────
        self._draw_status(p, cx, plat_y + R * 0.34, t, e, (r0, g0, b0))
        p.end()

    # ── pieces ───────────────────────────────────────────────────────
    def _draw_platform(self, p, cx, py, R, t, e, accent):
        r0, g0, b0 = accent
        rx = R * 1.18
        ry = rx * 0.26

        # glow pool on the platform
        pool = QRadialGradient(QPointF(cx, py), rx)
        pool.setColorAt(0, QColor(r0, g0, b0, int(70 + 60 * e)))
        pool.setColorAt(0.5, QColor(r0, g0, b0, 24))
        pool.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(pool))
        p.drawEllipse(QPointF(cx, py), rx, ry)

        # concentric rings
        for k, frac in enumerate((1.0, 0.72, 0.45)):
            a = int(120 - k * 30 + 50 * e)
            pen = QPen(QColor(r0, g0, b0, min(a, 200)))
            pen.setWidthF(1.4 if k == 0 else 0.9)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, py), rx * frac, ry * frac)

        # rotating tick ring (the projector feel)
        pen = QPen(QColor(255, 255, 255, int(70 + 90 * e)))
        pen.setWidthF(1.6)
        p.setPen(pen)
        for k in range(28):
            ang = t * 0.9 + k * (math.pi * 2 / 28)
            c, s = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(cx + c * rx * 0.88, py + s * ry * 0.88),
                       QPointF(cx + c * rx * 0.97, py + s * ry * 0.97))

        # bright centre
        core = QRadialGradient(QPointF(cx, py), rx * 0.2)
        core.setColorAt(0, QColor(255, 255, 255, int(140 + 80 * e)))
        core.setColorAt(1, QColor(r0, g0, b0, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, py), rx * 0.2, ry * 0.2)

    def _draw_beam(self, p, cx, cy, plat_y, R, e, accent):
        r0, g0, b0 = accent
        top_y = cy + R * 0.55
        half_top = R * 0.10
        half_bot = R * 0.55
        beam = QLinearGradient(cx, top_y, cx, plat_y)
        beam.setColorAt(0, QColor(r0, g0, b0, int(26 + 30 * e)))
        beam.setColorAt(1, QColor(r0, g0, b0, 6))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(beam))
        pts = [QPointF(cx - half_top, top_y), QPointF(cx + half_top, top_y),
               QPointF(cx + half_bot, plat_y), QPointF(cx - half_bot, plat_y)]
        p.drawPolygon(pts)

        # falling data particles
        for r in self.rain:
            f = r["p"]
            y = top_y + (plat_y - top_y) * f
            half = half_top + (half_bot - half_top) * f
            x = cx + r["x"] * half
            a = int(150 * (1 - f) + 30)
            p.setBrush(QBrush(QColor(180, 230, 255, a)))
            p.drawEllipse(QPointF(x, y), 1.1, 2.2)

    def _draw_status(self, p, cx, y, t, e, accent):
        r0, g0, b0 = accent
        dots = "." * (1 + int(t * 2.5) % 3)
        if self.mode == "thinking":
            label, col = f"THINKING{dots}", QColor(255, 200, 90)
        elif self.mode == "working":
            what = f" — {self.detail}" if self.detail else ""
            label, col = f"WORKING{dots}{what}", QColor(255, 160, 70)
        elif self.mode == "speaking":
            label, col = "SPEAKING", QColor(r0, g0, b0)
        else:
            label, col = "STANDING BY", QColor(90, 139, 176)

        f = QFont("Segoe UI", 9)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2.5)
        f.setBold(True)
        p.setFont(f)

        # pulse dot before the label
        pulse = 0.5 + 0.5 * math.sin(t * (5 if e > 0.3 else 1.6))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(label)
        dot_x = cx - tw / 2 - 12
        c = QColor(col); c.setAlpha(int(120 + 130 * pulse))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(dot_x, y - 4), 3.2, 3.2)

        p.setPen(QPen(col))
        p.drawText(QPointF(cx - tw / 2, y), label)

        # memory counter — the gold dots, counted
        if self._mem_count > 0:
            f2 = QFont("Segoe UI", 7)
            f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            f2.setBold(True)
            p.setFont(f2)
            mtxt = (f"{self._mem_count} "
                    f"MEMOR{'Y' if self._mem_count == 1 else 'IES'} FORMED")
            fm2 = p.fontMetrics()
            tw2 = fm2.horizontalAdvance(mtxt)
            gold = QColor(255, 200, 90, 190)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(gold))
            p.drawEllipse(QPointF(cx - tw2 / 2 - 9, y + 12), 2.2, 2.2)
            p.setPen(QPen(gold))
            p.drawText(QPointF(cx - tw2 / 2, y + 16), mtxt)
