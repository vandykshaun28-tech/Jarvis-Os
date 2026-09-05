"""
desktop_orb.py — ALLISON, always present.
─────────────────────────────────────────
A small, frameless, always-on-top orb that floats in the corner of the
WHOLE screen — over VS Code, the browser, everything. She's always
there while you work or talk, reflects her state (idle / listening /
thinking / speaking), and:

  • drag it anywhere with the mouse,
  • click it to bring the full Allison window to the front,
  • she's always listening for "Allison", so you can just talk to her.

It's a separate top-level window, so it stays put even when the main
Allison window is minimised or hidden to the tray.
"""

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtWidgets import QWidget

from ui.widgets.concept_orb import ConceptOrb


class DesktopOrb(QWidget):

    def __init__(self, controller=None, on_click=None):
        super().__init__(None)      # top-level, no parent
        self.controller = controller
        self.on_click = on_click
        self._press_pos = None
        self._moved = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)   # never steal focus
        self.setWindowTitle("Allison")

        self.resize(200, 220)
        self.orb = ConceptOrb(self)
        self.orb.pin_center = True                 # stay centred + small
        self.orb.setGeometry(0, 0, 200, 220)
        # let clicks/drags pass to THIS window, not be eaten as orb-spin
        self.orb.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.setToolTip("Allison — click to open, drag to move")
        self._place_default_corner()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(500)

    # ── position bottom-right of the primary screen by default ──
    def _place_default_corner(self):
        try:
            from PySide6.QtGui import QGuiApplication
            geo = QGuiApplication.primaryScreen().availableGeometry()
            self.move(geo.right() - self.width() - 24,
                      geo.bottom() - self.height() - 24)
        except Exception:
            self.move(1200, 700)

    def resizeEvent(self, event):
        self.orb.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    # ── drag to move / click to open ──
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint() - \
                self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._press_pos)
            self._moved = True

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._moved:
            if self.on_click:
                try:
                    self.on_click()
                except Exception:
                    pass
        self._press_pos = None

    # ── reflect her live state on the orb ──
    def _refresh(self):
        c = self.controller
        if c is None:
            return
        try:
            self.orb.set_memory_count(c.memory_count())
        except Exception:
            pass
        try:
            now, _ = c.brain_activity()
        except Exception:
            now = "idle"
        try:
            listening = bool(getattr(c, "listener", None) and
                             getattr(c.listener, "is_listening", False))
        except Exception:
            listening = False
        if now not in ("idle", "unknown", "starting up", ""):
            self.orb.set_working(now[:40])
        elif listening:
            self.orb.set_thinking()      # a gentle 'listening' shimmer
        else:
            self.orb.set_idle()
