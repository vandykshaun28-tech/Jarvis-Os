"""
console.py — the JARVIS conversation panel, v2.

Chat-app style: real message bubbles (you on the right in cyan, JARVIS
on the left in glass-dark), small centred system lines, dashed "tool
receipt" chips showing each action JARVIS takes, drag-and-drop files
and pictures with attachment chips, and a collapse button that folds
the whole panel into a slim rail.

The public API is unchanged from v1 (append_system / append_user /
append_agent / append_response / set_status / signals), so the rest of
the app plugs in untouched.
"""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QSizePolicy, QApplication,
)
from PySide6.QtCore import Signal, Qt, QTimer

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

CYAN   = "#22d3ee"
DIM    = "#5a8bb0"
ICE    = "#e8f6ff"
LINE   = "#12324a"
AMBER  = "#f5a623"
GREEN  = "#2ecc71"


class Bubble(QFrame):

    def __init__(self, text, kind):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        if kind == "you":
            who, who_col = "YOU", CYAN
            style = (f"QFrame{{background:rgba(34,211,238,0.10);"
                     f"border:1px solid rgba(34,211,238,0.30);"
                     f"border-radius:12px;}}")
        elif kind == "mind":
            who, who_col = "JARVIS · MIND", "#c084fc"
            style = (f"QFrame{{background:#101a2c;border:1px solid #2a2a4a;"
                     f"border-radius:12px;}}")
        else:
            who, who_col = "JARVIS", CYAN
            style = (f"QFrame{{background:#0c1826;border:1px solid {LINE};"
                     f"border-radius:12px;}}")
        self.setStyleSheet(style)

        head = QLabel(f"{who}   ·   {datetime.now().strftime('%H:%M')}")
        head.setStyleSheet(f"color:{who_col};font-size:9px;font-weight:700;"
                           f"letter-spacing:2px;border:none;background:transparent;")
        lay.addWidget(head)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(f"color:{ICE};font-size:12px;border:none;"
                           f"background:transparent;")
        lay.addWidget(body)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)


class Console(QWidget):

    commandSubmitted = Signal(str)
    filesSubmitted   = Signal(str, list)   # text, [file paths]
    muteClicked      = Signal()            # speaker button pressed

    def __init__(self):
        super().__init__()
        self._full_width = 400
        self.setFixedWidth(self._full_width)
        self.attachments = []
        self.collapsed = False
        self.transcript = []          # (time, who, text) — for copy-all
        self.setAcceptDrops(True)
        self.build_ui()

    # ── copy the whole conversation ─────────────
    def _log(self, who, text):
        self.transcript.append(
            (datetime.now().strftime("%H:%M:%S"), who, str(text)))
        if len(self.transcript) > 1000:
            self.transcript = self.transcript[-1000:]

    def set_mute_state(self, muted: bool):
        if muted:
            self.mute_btn.setText("🔇")
            self.mute_btn.setStyleSheet(
                f"QPushButton{{background:#2a1520;border:1px solid #ff5566aa;"
                f"border-radius:6px;color:#ff5566;font-size:11px;}}")
            self.mute_btn.setToolTip("JARVIS is muted — click to give him "
                                     "his voice back")
        else:
            self.mute_btn.setText("🔊")
            self.mute_btn.setStyleSheet(
                f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
                f"border-radius:6px;color:{DIM};font-size:11px;}}"
                f"QPushButton:hover{{border:1px solid {CYAN};color:{CYAN};}}")
            self.mute_btn.setToolTip("Stop speaking / mute JARVIS's voice")

    def copy_all(self):
        lines = [f"[{t}] {who}: {txt}" for t, who, txt in self.transcript]
        QApplication.clipboard().setText("\n".join(lines))
        old = self.copy_btn.text()
        self.copy_btn.setText("✓")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText(old))

    # ── build ───────────────────────────────────
    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # title row
        title_row = QHBoxLayout()
        self.title = QLabel("CONVERSATION")
        self.title.setStyleSheet(f"color:{CYAN};font-size:12px;font-weight:700;"
                                 f"letter-spacing:3px;border:none;")
        title_row.addWidget(self.title)
        title_row.addStretch()

        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(24, 24)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("Stop speaking / mute JARVIS's voice")
        self.mute_btn.setStyleSheet(
            f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
            f"border-radius:6px;color:{DIM};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid {CYAN};color:{CYAN};}}")
        self.mute_btn.clicked.connect(self.muteClicked.emit)
        title_row.addWidget(self.mute_btn)

        self.copy_btn = QPushButton("⧉")
        self.copy_btn.setFixedSize(24, 24)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy the whole conversation to the clipboard")
        self.copy_btn.setStyleSheet(
            f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
            f"border-radius:6px;color:{DIM};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid {CYAN};color:{CYAN};}}")
        self.copy_btn.clicked.connect(self.copy_all)
        title_row.addWidget(self.copy_btn)

        self.collapse_btn = QPushButton("❯")
        self.collapse_btn.setFixedSize(24, 24)
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.setToolTip("Collapse / expand the conversation panel")
        self.collapse_btn.setStyleSheet(
            f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
            f"border-radius:6px;color:{DIM};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid {CYAN};color:{CYAN};}}")
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        title_row.addWidget(self.collapse_btn)
        root.addLayout(title_row)

        # feed
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background:transparent;border:none;")
        self.scroll.viewport().setStyleSheet("background:transparent;")
        feed_holder = QWidget()
        feed_holder.setStyleSheet("background:transparent;")
        self.feed = QVBoxLayout(feed_holder)
        self.feed.setSpacing(10)
        self.feed.setContentsMargins(0, 0, 6, 0)
        self.feed.addStretch()
        self.scroll.setWidget(feed_holder)
        root.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda _, mx: self.scroll.verticalScrollBar().setValue(mx))

        # attachment chips
        self.chips = QLabel("")
        self.chips.setStyleSheet(
            f"color:{AMBER};font-size:11px;border:1px dashed {AMBER}55;"
            f"border-radius:8px;padding:7px;background:{AMBER}11;")
        self.chips.setWordWrap(True)
        self.chips.setCursor(Qt.PointingHandCursor)
        self.chips.setToolTip("Click to clear attachments")
        self.chips.mousePressEvent = self._clear_attachments
        self.chips.hide()
        root.addWidget(self.chips)

        # composer
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Message JARVIS — or drop files here…")
        self.input.returnPressed.connect(self.submit)
        self.input.setStyleSheet(
            f"QLineEdit{{background:#08111c;border:1px dashed {CYAN}44;"
            f"border-radius:10px;padding:11px;color:{ICE};"
            f"font-size:12px;}}"
            f"QLineEdit:focus{{border:1px solid {CYAN};}}")
        row.addWidget(self.input, 1)
        send = QPushButton("➤")
        send.setFixedSize(38, 38)
        send.setCursor(Qt.PointingHandCursor)
        send.setStyleSheet(
            f"QPushButton{{background:{CYAN};color:#04222f;border:none;"
            f"border-radius:10px;font-size:14px;font-weight:700;}}"
            f"QPushButton:hover{{background:#7ee6f7;}}")
        send.clicked.connect(self.submit)
        row.addWidget(send)
        self._composer_row = row
        self._send_btn = send
        root.addLayout(row)

        self.setStyleSheet(
            f"Console{{background:rgba(10,20,32,0.88);border:1px solid {LINE};"
            f"border-radius:12px;}}"
            f"QWidget{{background:transparent;border:none;}}")

        self.append_system("JARVIS Console Online.")

    # ── collapse ────────────────────────────────
    def toggle_collapsed(self):
        self.collapsed = not self.collapsed
        for w in (self.scroll, self.input, self._send_btn, self.title):
            w.setVisible(not self.collapsed)
        if self.collapsed:
            self.chips.hide()
            self.setFixedWidth(46)
            self.collapse_btn.setText("❮")
        else:
            self._refresh_chips()
            self.setFixedWidth(self._full_width)
            self.collapse_btn.setText("❯")

    # ── drag & drop ─────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self.collapsed:
                self.toggle_collapsed()
            self.input.setPlaceholderText("Drop it — I'll take a look, sir.")

    def dragLeaveEvent(self, event):
        self.input.setPlaceholderText("Message JARVIS — or drop files here…")

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isfile(path) and path not in self.attachments:
                self.attachments.append(path)
        self.input.setPlaceholderText("Message JARVIS — or drop files here…")
        self._refresh_chips()
        self.input.setFocus()

    def _refresh_chips(self):
        if not self.attachments:
            self.chips.hide()
            return
        names = []
        for p in self.attachments:
            icon = "🖼" if os.path.splitext(p)[1].lower() in IMAGE_EXTS else "📎"
            names.append(f"{icon} {os.path.basename(p)}")
        self.chips.setText("   ".join(names) + "    (click to clear)")
        self.chips.show()

    def _clear_attachments(self, *_):
        self.attachments = []
        self._refresh_chips()

    # ── feed helpers ────────────────────────────
    def _add(self, widget, align):
        row = QHBoxLayout()
        if align == "right":
            row.addStretch()
            row.addWidget(widget)
        elif align == "left":
            row.addWidget(widget)
            row.addStretch()
        else:
            row.addStretch()
            row.addWidget(widget)
            row.addStretch()
        self.feed.insertLayout(self.feed.count() - 1, row)
        # keep the feed bounded
        if self.feed.count() > 220:
            item = self.feed.takeAt(0)
            if item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def _sys_label(self, text, color=DIM, size=10):
        l = QLabel(text)
        l.setWordWrap(True)
        l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        l.setStyleSheet(f"color:{color};font-size:{size}px;border:none;"
                        f"background:transparent;")
        l.setMaximumWidth(int(self._full_width * 0.9))
        return l

    # ── public API (same names as v1) ───────────
    def append_system(self, text):
        text = str(text)
        self._log("SYSTEM", text)
        # tool receipts: "→ tool_name" from the brain's planning loop
        if text.startswith("→ "):
            chip = QLabel(f"✓ {text[2:].strip()}")
            chip.setStyleSheet(
                f"color:{GREEN};font-size:10px;border:1px dashed {LINE};"
                f"border-radius:7px;padding:3px 10px;background:transparent;")
            self._add(chip, "left")
            return
        # agent voices ("[Mind] ...", "[Trading] ...") get proper bubbles
        if text.startswith("[") and "]" in text[:12]:
            kind = "mind" if text.startswith("[Mind]") else "jarvis"
            self._add(Bubble(text, kind), "left")
            return
        # research/progress lines keep their emoji styling but stay subtle
        self._add(self._sys_label(text), "center")

    def set_status(self, text):
        if text in ("Ready", "Thinking..."):
            return  # bubbles + receipts already tell the story
        self.append_system(text)

    def append_system_text(self, text):
        self.append_system(text)

    def append_user(self, text):
        self._log("YOU", text)
        self._add(Bubble(str(text), "you"), "right")

    def append_agent(self, role, text):
        self._log(role.upper(), text)
        self._add(Bubble(f"[{role}] {text}", "jarvis"), "left")

    def append_response(self, text):
        text = str(text)
        self._log("JARVIS", text)
        kind = "mind" if text.startswith("[Mind]") else "jarvis"
        self._add(Bubble(text, kind), "left")

    # ── submit ──────────────────────────────────
    def submit(self):
        text = self.input.text().strip()
        if not text and not self.attachments:
            return
        if self.attachments:
            files = list(self.attachments)
            shown = text or "(no message — analyse the attached files)"
            names = ", ".join(os.path.basename(p) for p in files)
            self.append_user(f"{shown}\n📎 {names}")
            self.filesSubmitted.emit(shown, files)
            self._clear_attachments()
        else:
            self.append_user(text)
            self.commandSubmitted.emit(text)
        self.input.clear()
