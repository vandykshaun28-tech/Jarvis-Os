"""
concept_orb.py — ALLISON's core, JARVIS-style.
──────────────────────────────────────────────
Clean, minimal, electric cyan-blue (Huw-Prosser / Iron-Man look):

  • IDLE / SPEAKING  → the full core: a bright arc-reactor centre, a few
    tilted orbital rings with light circling them, a light particle
    halo and a HUD reticle. Lots of empty space — not a dense cloud.
  • THINKING / WORKING → she automatically shrinks into a SMALL SPINNING
    ORB in the top corner and gets out of the way while the task /
    panels take the screen. Snaps back to centre when she's done.

Drop-in API (unchanged):
    set_idle() / set_thinking() / set_speaking() / set_working(detail)
    set_compact(bool)          — force the corner orb (panels/mini-mode)
    set_memory_count(int)      — kept for the small counter text
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget


def _accent_rgb():
    try:
        from ui.styles.theme_manager import pal
        hexc = pal().get("accent", "#3dd8ff").lstrip("#")
        return tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (61, 216, 255)


def _halo_points(n, rng):
    """A light spherical halo of motes around the core — sparse, so it
    reads as a clean holographic shell, not a dense particle cloud."""
    pts = []
    for _ in range(n):
        u = rng.uniform(0, math.pi * 2)
        v = math.acos(rng.uniform(-1, 1))
        r = 1.0 + rng.uniform(-0.12, 0.22)
        pts.append([math.sin(v) * math.cos(u) * r * 1.14,
                    math.cos(v) * r * 0.9,
                    math.sin(v) * math.sin(u) * r * 1.14])
    return pts


class ConceptOrb(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "idle"
        self.detail = ""
        self.t = 0.0
        self._energy = 0.0
        self.compact = False          # external force (panels / mini-mode)
        self._compact_eff = False     # effective (external OR busy)
        self.pin_center = False       # desktop overlay: always centred+small
        self._scale_now = 1.0

        rng = random.Random(23)
        # a light halo (much sparser than the old bloom)
        self.pts = _halo_points(300, rng)
        self.phase = [rng.random() * math.pi * 2 for _ in self.pts]
        self._rng = rng

        # orbital rings — each a tilted circle her light travels around
        self.rings = [
            {"ax": 0.0, "tilt": 0.62, "r": 1.30, "spd": 0.9,  "beads": 2},
            {"ax": 1.1, "tilt": 0.42, "r": 1.15, "spd": -0.7, "beads": 2},
            {"ax": 2.2, "tilt": 0.78, "r": 1.45, "spd": 0.55, "beads": 1},
        ]

        # firing motes (sparks racing out) — the "thinking" cue
        self._sparks = []

        # memory count kept ONLY for the small counter text — no more
        # gold dots cluttering the centre.
        self._mem_count = 0

        self.yaw = 0.5
        self.pitch = -0.15
        self._drag = None
        self._auto = True
        self.setCursor(Qt.OpenHandCursor)

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(33)

    # ── public state API (drop-in) ───────────────────────────────────
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
        self._mem_count = max(0, int(n))

    # ── animation clock ──────────────────────────────────────────────
    def _tick(self):
        target = {"thinking": 1.0, "working": 1.0, "speaking": 0.55}\
            .get(self.mode, 0.12)
        self._energy += (target - self._energy) * 0.07
        e = self._energy
        self.t += 0.016 + e * 0.02
        if self._auto:
            self.yaw += 0.0045 + e * 0.006

        # she goes to the corner when busy (thinking/working) OR when
        # something external (a panel, mini-mode) forces it. When pinned
        # (the desktop overlay) she stays centred+small no matter what.
        busy = self.mode in ("thinking", "working")
        self._compact_eff = False if self.pin_center else (self.compact or busy)

        # firing motes
        rate = 0.04 + e * 0.5
        if self._rng.random() < rate and len(self._sparks) < 30:
            self._sparks.append([self._rng.randrange(len(self.pts)),
                                 0.0, self._rng.uniform(0.03, 0.07)])
        for s in self._sparks:
            s[1] += s[2] * (1.0 + e)
        self._sparks = [s for s in self._sparks if s[1] < 1.0]

        tgt = 0.42 if self._compact_eff else 1.0
        self._scale_now += (tgt - self._scale_now) * 0.14
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

    # ── projection helper ────────────────────────────────────────────
    def _projector(self, cx, cy, R):
        cyaw, syaw = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)

        def project(x, y, z):
            x1 = x * cyaw + z * syaw
            z1 = -x * syaw + z * cyaw
            y2 = y * cp - z1 * sp
            z2 = y * sp + z1 * cp
            f = 1.7 / (z2 + 2.6)
            return cx + x1 * R * f, cy - y2 * R * f, z2
        return project

    def _ring_paths(self, project):
        out = []
        for ring in self.rings:
            seg = 84
            ca, sa = math.cos(ring["ax"]), math.sin(ring["ax"])
            tilt = ring["tilt"]
            path = []
            for k in range(seg + 1):
                a = k / seg * math.pi * 2
                x = math.cos(a) * ring["r"]
                z = math.sin(a) * ring["r"]
                y = z * math.sin(tilt)
                z = z * math.cos(tilt)
                x2 = x * ca + z * sa
                z2 = -x * sa + z * ca
                path.append(project(x2, y, z2))
            out.append((ring, path))
        return out

    def _draw_core(self, p, cx, cy, R, e, t):
        r0, g0, b0 = _accent_rgb()
        core_r = R * (0.32 + 0.03 * math.sin(t * 1.4) + 0.05 * e)
        halo = QRadialGradient(QPointF(cx, cy), core_r * 2.3)
        halo.setColorAt(0.0, QColor(255, 255, 255, int(60 + 60 * e)))
        halo.setColorAt(0.35, QColor(r0, g0, b0, int(70 + 60 * e)))
        halo.setColorAt(1.0, QColor(r0, g0, b0, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), core_r * 2.3, core_r * 2.3)
        body = QRadialGradient(QPointF(cx, cy), core_r)
        body.setColorAt(0.0, QColor(255, 255, 255, 255))
        body.setColorAt(0.32, QColor(215, 244, 255, 245))
        body.setColorAt(0.72, QColor(r0, g0, b0, 220))
        body.setColorAt(1.0, QColor(r0, g0, b0, 40))
        p.setBrush(QBrush(body))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)
        return core_r

    def _draw_rings(self, p, ring_polys, e, t, beads=True):
        r0, g0, b0 = _accent_rgb()

        def draw_half(path, back):
            for k in range(len(path) - 1):
                x1, y1, z1 = path[k]
                x2, y2, z2 = path[k + 1]
                zmid = (z1 + z2) / 2
                if (zmid < 0) != back:
                    continue
                d = max(0.15, min(1.0, (zmid + 1.4) / 2.8))
                a = int(min(190, (30 + 90 * d) * (0.55 + 0.6 * e)))
                pen = QPen(QColor(r0, g0, b0, a))
                pen.setWidthF((1.0 + 1.0 * d) * (0.7 if back else 1.0))
                p.setPen(pen)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        for _, path in ring_polys:
            draw_half(path, back=True)
        yield  # (marker) core drawn between halves by caller
        for _, path in ring_polys:
            draw_half(path, back=False)
        if beads:
            for ring, path in ring_polys:
                seg = len(path) - 1
                for bi in range(ring["beads"]):
                    phase = (t * ring["spd"] * (0.4 + e * 0.7)
                             + bi / max(1, ring["beads"])) % 1.0
                    fi = phase * seg
                    i0 = int(fi) % seg
                    frac = fi - int(fi)
                    x1, y1, z1 = path[i0]
                    x2, y2, z2 = path[i0 + 1]
                    bx = x1 + (x2 - x1) * frac
                    by = y1 + (y2 - y1) * frac
                    d = max(0.25, min(1.0, ((z1 + z2) / 2 + 1.4) / 2.8))
                    glow = QRadialGradient(bx, by, 6 * d + 2)
                    glow.setColorAt(0, QColor(255, 255, 255, int(230 * d)))
                    glow.setColorAt(0.5, QColor(r0, g0, b0, int(180 * d)))
                    glow.setColorAt(1, QColor(r0, g0, b0, 0))
                    p.setBrush(QBrush(glow)); p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(bx, by), 6 * d + 2, 6 * d + 2)

    # ── painting ─────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        t, e = self.t, self._energy
        s = self._scale_now
        compact = self._compact_eff and s < 0.85

        # desktop overlay: clean minimal orb, always centred in its window
        if self.pin_center:
            cx, cy = W / 2, H / 2 - min(W, H) * 0.06
            R = min(W, H) * 0.30
            self._paint_compact(p, cx, cy, R, t, e)
            p.end()
            return

        if self._compact_eff:
            # slide down into the BOTTOM-right corner as she shrinks —
            # matching Huw's Jarvis. Margin leaves room for the name label.
            mx = min(W, H) * 0.24
            my = min(W, H) * 0.30
            cx = W / 2 + (W * 0.5 - mx) * (1 - s) / 0.58
            cy = H / 2 + (H * 0.5 - my) * (1 - s) / 0.58
        else:
            cx, cy = W / 2, H / 2 - min(W, H) * 0.05
        R = min(W, H) * 0.30 * s

        if compact:
            self._paint_compact(p, cx, cy, R, t, e)
        else:
            self._paint_full(p, cx, cy, R, t, e)
        p.end()

    # ── COMPACT: a clean small spinning orb ──────────────────────────
    def _paint_compact(self, p, cx, cy, R, t, e):
        r0, g0, b0 = _accent_rgb()
        project = self._projector(cx, cy, R)
        ring_polys = self._ring_paths(project)

        # soft pool
        pool = QRadialGradient(cx, cy, R * 1.9)
        pool.setColorAt(0, QColor(r0, g0, b0, int(34 + 40 * e)))
        pool.setColorAt(1, QColor(2, 6, 13, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(pool))
        p.drawEllipse(QPointF(cx, cy), R * 1.9, R * 1.9)

        gen = self._draw_rings(p, ring_polys, e, t, beads=True)
        next(gen)                       # back halves
        self._draw_core(p, cx, cy, R, e, t)
        try:
            next(gen)                   # front halves + beads
        except StopIteration:
            pass

        # a single thin rotating reticle arc — the "spinning" tell
        pen = QPen(QColor(255, 255, 255, int(120 + 100 * min(1, e))))
        pen.setWidthF(1.8); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        ar = R * 1.35
        rect = QRectF(cx - ar, cy - ar, ar * 2, ar * 2)
        start = int((-t * 200) % 360) * 16
        p.drawArc(rect, start, 60 * 16)
        p.drawArc(rect, start + 180 * 16, 60 * 16)

        # ── name label + tiny status under the corner orb (like his
        #    "JARVIS" caption) ──
        fn = QFont("Segoe UI", 8)
        fn.setLetterSpacing(QFont.AbsoluteSpacing, 3.5)
        fn.setBold(True)
        p.setFont(fn)
        p.setPen(QPen(QColor(235, 248, 255, 220)))
        fm = p.fontMetrics()
        nm = "ALLISON"
        tw = fm.horizontalAdvance(nm)
        p.drawText(QPointF(cx - tw / 2, cy + ar + R * 0.34), nm)

        state = {"thinking": "THINKING", "working": "WORKING"}\
            .get(self.mode, "ONLINE")
        fs = QFont("Segoe UI", 6)
        fs.setLetterSpacing(QFont.AbsoluteSpacing, 2.0)
        fs.setBold(True)
        p.setFont(fs)
        p.setPen(QPen(QColor(r0, g0, b0, 170)))
        fm2 = p.fontMetrics()
        tw2 = fm2.horizontalAdvance(state)
        p.drawText(QPointF(cx - tw2 / 2, cy + ar + R * 0.60), state)

    # ── FULL: the centre core, decluttered (no gold memory dots) ─────
    def _paint_full(self, p, cx, cy, R, t, e):
        r0, g0, b0 = _accent_rgb()
        project = self._projector(cx, cy, R)

        # ambient pool
        pool = QRadialGradient(cx, cy, R * 1.9)
        pool.setColorAt(0, QColor(r0, g0, b0, int(26 + 36 * e)))
        pool.setColorAt(1, QColor(2, 6, 13, 0))
        p.setBrush(QBrush(pool)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), R * 1.9, R * 1.9)

        ring_polys = self._ring_paths(project)

        # back ring halves
        gen = self._draw_rings(p, ring_polys, e, t, beads=True)
        next(gen)

        # core
        self._draw_core(p, cx, cy, R, e, t)

        # light halo motes (sparse, clean — sorted back to front)
        proj = [project(x, y, z) for (x, y, z) in self.pts]
        p.setPen(Qt.NoPen)
        order = sorted(range(len(proj)), key=lambda k: proj[k][2])
        for k in order:
            px, py, z2 = proj[k]
            dfront = max(0.2, min(1.0, (z2 + 1.4) / 2.8))
            tw = 0.55 + 0.45 * math.sin(t * 1.4 + self.phase[k])
            cr = int(r0 + (255 - r0) * 0.35 * e)
            cg = int(g0 + (255 - g0) * 0.35 * e)
            cb = int(b0 + (255 - b0) * 0.20 * e)
            sz = 1.0 + 0.9 * dfront
            alpha = int((55 + 130 * dfront) * tw)
            p.setBrush(QBrush(QColor(cr, cg, cb, alpha)))
            p.drawEllipse(QPointF(px, py), sz, sz)

        # firing sparks
        for idx, ft, _ in self._sparks:
            px0, py0, z0 = proj[idx]
            px = cx + (px0 - cx) * ft
            py = cy + (py0 - cy) * ft
            d = max(0.2, min(1.0, (z0 + 1.4) / 2.8))
            glow = QRadialGradient(px, py, 6)
            glow.setColorAt(0, QColor(255, 255, 255, int(220 * d)))
            glow.setColorAt(0.4, QColor(r0, g0, b0, int(160 * d)))
            glow.setColorAt(1, QColor(r0, g0, b0, 0))
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(px, py), 6, 6)

        # front ring halves + beads
        try:
            next(gen)
        except StopIteration:
            pass

        # HUD reticle: measurement ring + rotating target-lock brackets
        self._draw_hud(p, cx, cy, R, t, e)

        # busy spinner arc
        if e > 0.25 and self.mode in ("thinking", "working"):
            pen = QPen(QColor(255, 255, 255, int(190 * min(1, e))))
            pen.setWidthF(2.0); pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            ar = R * 1.5
            rect = QRectF(cx - ar, cy - ar, ar * 2, ar * 2)
            start = int((-t * 240) % 360) * 16
            p.drawArc(rect, start, 66 * 16)
            p.drawArc(rect, start + 180 * 16, 66 * 16)

        # status readout + small memory counter, well below the core
        self._draw_status(p, cx, cy + R * 1.62, t, e)

    # ── HUD reticle ──────────────────────────────────────────────────
    def _draw_hud(self, p, cx, cy, R, t, e):
        r0, g0, b0 = _accent_rgb()
        p.setBrush(Qt.NoBrush)
        tick_r = R * 1.42
        n = 72
        for k in range(n):
            ang = t * 0.12 + k * (2 * math.pi / n)
            longt = (k % 6 == 0)
            r1 = tick_r
            r2 = tick_r + (R * 0.06 if longt else R * 0.028)
            a = int(min(160, (30 + 44 * e) * (1.0 if longt else 0.55)))
            pen = QPen(QColor(r0, g0, b0, a))
            pen.setWidthF(1.4 if longt else 0.8)
            p.setPen(pen)
            c, s = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(cx + c * r1, cy + s * r1),
                       QPointF(cx + c * r2, cy + s * r2))
        pen = QPen(QColor(r0, g0, b0, int(22 + 28 * e)))
        pen.setWidthF(1.0); p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), tick_r, tick_r)
        br = R * (1.56 - 0.12 * e)
        ba = -t * 0.22
        pen = QPen(QColor(215, 244, 255, int(85 + 90 * e)))
        pen.setWidthF(2.0); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        rect = QRectF(cx - br, cy - br, br * 2, br * 2)
        for corner in range(4):
            start = int(math.degrees(ba + corner * (math.pi / 2)) * 16)
            p.drawArc(rect, start - 15 * 16, 30 * 16)
            ca = ba + corner * (math.pi / 2)
            c, s = math.cos(ca), math.sin(ca)
            p.drawLine(QPointF(cx + c * (br - R * 0.05), cy + s * (br - R * 0.05)),
                       QPointF(cx + c * (br + R * 0.05), cy + s * (br + R * 0.05)))

    def _draw_status(self, p, cx, y, t, e):
        r0, g0, b0 = _accent_rgb()
        dots = "." * (1 + int(t * 2.5) % 3)
        if self.mode == "thinking":
            label, col = f"THINKING{dots}", QColor(120, 210, 255)
        elif self.mode == "working":
            what = f" — {self.detail}" if self.detail else ""
            label, col = f"WORKING{dots}{what}", QColor(120, 210, 255)
        elif self.mode == "speaking":
            label, col = "SPEAKING", QColor(r0, g0, b0)
        else:
            label, col = "STANDING BY", QColor(90, 140, 175)

        f = QFont("Segoe UI", 9)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2.5)
        f.setBold(True)
        p.setFont(f)
        pulse = 0.5 + 0.5 * math.sin(t * (5 if e > 0.3 else 1.6))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(label)
        c = QColor(col); c.setAlpha(int(120 + 130 * pulse))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(cx - tw / 2 - 12, y - 4), 3.2, 3.2)
        p.setPen(QPen(col))
        p.drawText(QPointF(cx - tw / 2, y), label)

        if self._mem_count > 0:
            f2 = QFont("Segoe UI", 7)
            f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
            f2.setBold(True)
            p.setFont(f2)
            mtxt = (f"{self._mem_count} "
                    f"MEMOR{'Y' if self._mem_count == 1 else 'IES'}")
            fm2 = p.fontMetrics()
            tw2 = fm2.horizontalAdvance(mtxt)
            dimc = QColor(r0, g0, b0, 150)
            p.setPen(QPen(dimc))
            p.drawText(QPointF(cx - tw2 / 2, y + 15), mtxt)
