"""
info_panel.py — the "mini tab": whenever JARVIS looks something up or
has data to show, it can pop up here instead of only being buried in
the chat log. Modelled on Tony Stark's HUD: draggable from the title
bar, resizable from the bottom-right corner, one click to enlarge.

Multiple panels can be open at once (weather here, a file listing
there); each is identified by a panel_id so a repeat request updates
the same panel in place instead of spawning a new one.
"""

import html as _html
import os

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QPixmap, QColor
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QTextBrowser,
)


class InfoPanel(QFrame):

    TITLE_H = 34
    GRIP = 16
    W_COMPACT, H_COMPACT = 320, 240
    W_LARGE, H_LARGE = 620, 460
    MIN_W, MIN_H = 220, 130

    def __init__(self, panel_id: str, parent=None):
        super().__init__(parent)
        self.panel_id = panel_id
        self.on_close = None   # set by the window to update brain state
        self.enlarged = False
        self.user_moved = False
        self.user_resized = False
        self._pre_enlarge_geom = None
        self._drag_offset = None
        self._resizing = False
        self._resize_start = None

        self.setMouseTracking(True)
        self.resize(self.W_COMPACT, self.H_COMPACT)
        self.setMinimumSize(self.MIN_W, self.MIN_H)
        self.setStyleSheet(
            "QFrame{background:rgba(8,17,28,0.96);border:1px solid #22d3ee55;"
            "border-radius:12px;}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.title_label = QLabel("JARVIS")
        self.title_label.setStyleSheet(
            "color:#22d3ee;font-size:10px;font-weight:700;"
            "letter-spacing:1px;border:none;background:transparent;")
        top.addWidget(self.title_label, 1)

        self.enlarge_btn = QPushButton("\u2922")   # expand icon
        self.enlarge_btn.setFixedSize(20, 20)
        self.enlarge_btn.setCursor(Qt.PointingHandCursor)
        self.enlarge_btn.setToolTip("Enlarge / restore")
        self.enlarge_btn.setStyleSheet(self._btn_style())
        self.enlarge_btn.clicked.connect(self.toggle_enlarge)
        top.addWidget(self.enlarge_btn)

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(self._btn_style(hover="#ff5566"))
        close_btn.clicked.connect(self._closed)
        top.addWidget(close_btn)
        lay.addLayout(top)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(
            "QTextBrowser{background:#04080f;border:none;border-radius:8px;"
            "color:#dbe9f5;padding:8px;}")
        lay.addWidget(self.browser, 1)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "background:#04080f;border:none;border-radius:8px;")
        self.image_label.hide()
        lay.addWidget(self.image_label, 1)

        self.hide()

    def _closed(self):
        self.hide()
        if callable(self.on_close):
            try:
                self.on_close()
            except Exception:
                pass

    @staticmethod
    def _btn_style(hover="#22d3ee"):
        return (
            "QPushButton{background:#0d1e2e;border:1px solid #12324a;"
            "border-radius:5px;color:#5a8bb0;font-size:11px;}"
            f"QPushButton:hover{{border:1px solid {hover};color:{hover};}}")

    # ── content ──────────────────────────────────
    def set_content(self, title: str, content: str, kind: str = "text"):
        self.title_label.setText(("\u25c9 " + title)[:70])
        if kind == "image" and content and os.path.exists(content):
            pix = QPixmap(content)
            if not pix.isNull():
                self.browser.hide()
                self.image_label.show()
                self._raw_pixmap = pix
                self._rescale_image()
                return
        # text (default / fallback if image failed to load)
        self.image_label.hide()
        self.browser.show()
        self.browser.setHtml(self._to_html(content or ""))

    def _to_html(self, text: str) -> str:
        escaped = _html.escape(text).replace("\n", "<br>")
        return (
            "<div style='font-family:Consolas,\"Cascadia Code\",monospace;"
            f"font-size:12px;line-height:1.55;'>{escaped}</div>")

    def _rescale_image(self):
        if hasattr(self, "_raw_pixmap") and not self._raw_pixmap.isNull():
            scaled = self._raw_pixmap.scaled(
                self.image_label.width(), self.image_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)

    # ── enlarge / restore ────────────────────────
    def toggle_enlarge(self):
        parent = self.parentWidget()
        if not self.enlarged:
            self._pre_enlarge_geom = (self.pos(), self.size())
            w = min(self.W_LARGE, parent.width() - 40) if parent else self.W_LARGE
            h = min(self.H_LARGE, parent.height() - 40) if parent else self.H_LARGE
            self.resize(w, h)
            self.enlarge_btn.setText("\u2925")   # restore icon
            self.enlarged = True
        else:
            if self._pre_enlarge_geom:
                pos, size = self._pre_enlarge_geom
                self.resize(size)
                self.move(pos)
            self.enlarge_btn.setText("\u2922")
            self.enlarged = False
        self._clamp_to_parent()
        self._rescale_image()

    def _clamp_to_parent(self):
        parent = self.parentWidget()
        if not parent:
            return
        x = max(0, min(self.x(), parent.width() - self.width()))
        y = max(0, min(self.y(), parent.height() - self.height()))
        self.move(x, y)

    # ── drag (title bar) + resize (corner grip) ──
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        if self._in_grip(pos):
            self._resizing = True
            self._resize_start = (pos, self.size())
        elif pos.y() <= self.TITLE_H:
            self._drag_offset = pos

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._resizing and self._resize_start:
            start_pos, start_size = self._resize_start
            delta = pos - start_pos
            parent = self.parentWidget()
            max_w = (parent.width() - self.x()) if parent else 4000
            max_h = (parent.height() - self.y()) if parent else 4000
            w = max(self.MIN_W, min(start_size.width() + delta.x(), max_w))
            h = max(self.MIN_H, min(start_size.height() + delta.y(), max_h))
            self.resize(w, h)
            self.user_resized = True
            self._rescale_image()
            return
        if self._drag_offset is not None:
            new_pos = self.mapToParent(pos - self._drag_offset)
            parent = self.parentWidget()
            if parent:
                x = max(0, min(new_pos.x(), parent.width() - self.width()))
                y = max(0, min(new_pos.y(), parent.height() - self.height()))
                self.move(x, y)
                self.user_moved = True
            return
        # hover cursor feedback only
        if self._in_grip(pos):
            self.setCursor(Qt.SizeFDiagCursor)
        elif pos.y() <= self.TITLE_H:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._resizing = False
        self._resize_start = None
        self.setCursor(Qt.ArrowCursor)

    def _in_grip(self, pos) -> bool:
        return (pos.x() >= self.width() - self.GRIP
                and pos.y() >= self.height() - self.GRIP)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_image()

    # ── draw a small resize-grip glyph in the corner ─
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#22d3ee88")))
        r = self.rect()
        for i in (4, 9, 14):
            painter.drawLine(
                QRectF(r.right() - i, r.bottom() - 2,
                       r.right() - 2, r.bottom() - i).topLeft(),
                QRectF(r.right() - i, r.bottom() - 2,
                       r.right() - 2, r.bottom() - i).bottomRight())
        painter.end()
