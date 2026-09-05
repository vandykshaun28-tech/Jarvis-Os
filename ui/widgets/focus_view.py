"""
focus_view.py — FULL-SCREEN "JARVIS" mode (Huw-Prosser style).
───────────────────────────────────────────────────────────────
An overlay that sits on top of the whole window. When it's on:

  • IDLE   → nothing but the orb, alone on the grid. Clean.
  • TASK   → whatever Allison produces (a report, a search result, an
             image, a page) fills the screen, and the orb drops into
             the bottom-right corner. A small EXIT chip returns to the
             normal dashboard.

It's an OVERLAY — the real dashboard is untouched behind it, so if
anything ever looks wrong you just exit focus mode and everything is
exactly as before.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QPushButton,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap

from ui.widgets.concept_orb import ConceptOrb


def _pal():
    try:
        from ui.styles.theme_manager import pal
        return pal()
    except Exception:
        return {"accent": "#3dd8ff", "panel": "#08131f", "line": "#123048",
                "text": "#dff2ff", "text2": "#7fa6c2", "canvas": "#02060d"}


class FocusView(QWidget):

    def __init__(self, parent=None, activity_provider=None,
                 memory_provider=None, on_exit=None):
        super().__init__(parent)
        self.activity_provider = activity_provider
        self.memory_provider = memory_provider
        self.on_exit = on_exit
        self._has_content = False

        # the orb fills the whole view; it centres itself when idle and
        # slides to the bottom-right corner on its own when busy.
        self.orb = ConceptOrb(self)

        # ── task content surface (hidden until there's something) ──
        self.card = QFrame(self)
        self.card.hide()
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(26, 20, 26, 22)
        lay.setSpacing(10)

        self.title = QLabel("")
        lay.addWidget(self.title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse |
                                          Qt.LinksAccessibleByMouse)
        self.body.setOpenExternalLinks(True)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image = QLabel("")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.hide()
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.image)
        hl.addWidget(self.body)
        hl.addStretch()
        self.scroll.setWidget(holder)
        lay.addWidget(self.scroll, 1)

        # exit chip
        self.exit_btn = QPushButton("‹  EXIT FOCUS", self)
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.clicked.connect(lambda: self.on_exit and self.on_exit())

        self.retheme()

        # drive the orb + auto-clear from live activity
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(600)

    # ── theming ──────────────────────────────────────────────────────
    def retheme(self):
        p = _pal()
        self.card.setStyleSheet(
            f"QFrame{{background:rgba(8,19,31,0.86);"
            f"border:1px solid {p['accent']}44;border-radius:16px;}}")
        self.title.setStyleSheet(
            f"color:{p['accent']};font-size:13px;font-weight:800;"
            "letter-spacing:3px;border:none;background:transparent;")
        self.body.setStyleSheet(
            f"color:{p['text']};font-size:14px;border:none;"
            "background:transparent;")
        self.scroll.setStyleSheet("background:transparent;border:none;")
        self.scroll.viewport().setStyleSheet("background:transparent;")
        self.exit_btn.setStyleSheet(
            f"QPushButton{{background:{p['panel']};color:{p['text2']};"
            f"border:1px solid {p['line']};border-radius:9px;padding:6px 12px;"
            "font-size:11px;font-weight:700;letter-spacing:1px;}}"
            f"QPushButton:hover{{border:1px solid {p['accent']};"
            f"color:{p['accent']};}}")

    # ── layout ───────────────────────────────────────────────────────
    def resizeEvent(self, event):
        W, H = self.width(), self.height()
        self.orb.setGeometry(0, 0, W, H)
        # task card fills most of the screen, leaving the bottom-right
        # corner clear for the orb
        m = int(min(W, H) * 0.06)
        cw = int(W - 2 * m)
        ch = int(H - 2 * m - min(W, H) * 0.14)   # leave room bottom for orb
        self.card.setGeometry(m, m, cw, max(120, ch))
        self.exit_btn.adjustSize()
        self.exit_btn.move(m, m // 2)
        super().resizeEvent(event)

    # ── content API ──────────────────────────────────────────────────
    def show_content(self, title, content, kind="text"):
        self._has_content = True
        self.title.setText(str(title).upper()[:60])
        if kind == "image":
            pix = QPixmap(str(content))
            if not pix.isNull():
                mw = max(200, self.card.width() - 80)
                if pix.width() > mw:
                    pix = pix.scaledToWidth(mw, Qt.SmoothTransformation)
                self.image.setPixmap(pix)
                self.image.show()
                self.body.setText("")
            else:
                self.image.hide()
                self.body.setText(f"(couldn't load image: {content})")
        else:
            self.image.hide()
            self.body.setText(self._light_md(str(content)))
        self.card.show()
        self.card.raise_()
        self.exit_btn.raise_()
        # nudge the orb into the corner immediately
        try:
            self.orb.set_compact(True)
        except Exception:
            pass

    def clear_content(self):
        self._has_content = False
        self.card.hide()
        try:
            self.orb.set_compact(False)
        except Exception:
            pass

    def _light_md(self, text):
        import html as _h
        import re as _re
        t = _h.escape(text)
        t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = _re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
        t = t.replace("\n", "<br>")
        return t

    # ── live refresh: drive the orb, auto-clear when idle a while ────
    def _refresh(self):
        if not self.isVisible():
            return
        try:
            if self.memory_provider:
                self.orb.set_memory_count(self.memory_provider())
        except Exception:
            pass
        try:
            now = "idle"
            if self.activity_provider:
                now, _ = self.activity_provider()
            busy = now not in ("idle", "unknown", "starting up", "")
            if busy:
                self.orb.set_working(now[:50])
            elif not self._has_content:
                self.orb.set_idle()
        except Exception:
            pass
