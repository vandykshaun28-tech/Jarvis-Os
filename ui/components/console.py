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
    QLineEdit, QPlainTextEdit, QScrollArea, QFrame, QSizePolicy,
    QApplication,
)
from PySide6.QtCore import Signal, Qt, QTimer

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

CYAN   = "#22d3ee"
DIM    = "#5a8bb0"
ICE    = "#e8f6ff"
LINE   = "#12324a"
AMBER  = "#f5a623"
GREEN  = "#2ecc71"

import html as _html
import re as _re

from ui.styles.theme_manager import pal


def _md_to_html(text: str) -> str:
    """Small markdown → HTML so JARVIS's replies render like a modern
    chat: bold, italics, inline code, fenced code blocks, headers,
    bullet/numbered lists, links."""
    p = pal()
    code_css = (f"background:{p['code_bg']};border:1px solid {p['line']};"
                f"border-radius:6px;")

    # pull out fenced code blocks first so nothing inside gets mangled
    blocks = []
    def _stash(m):
        blocks.append(m.group(1))
        return f"\x00BLOCK{len(blocks)-1}\x00"
    text = _re.sub(r"```[a-zA-Z0-9_+-]*\n?(.*?)```", _stash, text,
                   flags=_re.S)

    text = _html.escape(text)

    # headers
    text = _re.sub(r"^### (.+)$",
                   r"<span style='font-size:13px;font-weight:700;'>\1</span>",
                   text, flags=_re.M)
    text = _re.sub(r"^## (.+)$",
                   r"<span style='font-size:14px;font-weight:700;'>\1</span>",
                   text, flags=_re.M)
    text = _re.sub(r"^# (.+)$",
                   r"<span style='font-size:15px;font-weight:700;'>\1</span>",
                   text, flags=_re.M)
    # bold / italic / inline code
    text = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = _re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = _re.sub(r"`([^`\n]+)`",
                   rf"<code style='{code_css}padding:1px 4px;'>\1</code>",
                   text)
    # links
    text = _re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                   rf"<a href='\2' style='color:{p['accent']};'>\1</a>", text)
    text = _re.sub(r"(?<!['\"=>])(https?://[^\s<]+)",
                   rf"<a href='\1' style='color:{p['accent']};'>\1</a>", text)
    # bullet + numbered lists (simple, line-based)
    text = _re.sub(r"^[-•] (.+)$", r"&nbsp;&nbsp;•&nbsp;\1", text, flags=_re.M)
    text = _re.sub(r"^(\d+)\. (.+)$", r"&nbsp;&nbsp;\1.&nbsp;\2", text,
                   flags=_re.M)

    # collapse runs of blank lines — tool-heavy replies used to stack
    # <br><br><br> and blow the bubble up with empty space
    text = _re.sub(r"\n{3,}", "\n\n", text.strip())
    text = text.replace("\n", "<br>")

    # restore code blocks as styled <pre>
    for i, code in enumerate(blocks):
        pre = (f"<pre style='{code_css}padding:6px;margin:2px 0;"
               f"font-family:Consolas,monospace;font-size:11px;"
               f"white-space:pre-wrap;'>{_html.escape(code.strip())}</pre>")
        text = text.replace(f"\x00BLOCK{i}\x00", pre)
    # <br> straight after a <pre> block doubles the gap — drop it
    text = _re.sub(r"</pre>(<br>)+", "</pre>", text)
    text = _re.sub(r"(<br>)+<pre", "<pre", text)
    return text


class Bubble(QFrame):

    MAX_W = 330   # hard cap — word-wrapped labels NEED a known width,
                  # otherwise Qt's height-for-width maths pads bubbles
                  # (and the whole feed) with huge phantom gaps

    def __init__(self, text, kind):
        super().__init__()
        self.kind = kind
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 7)
        lay.setSpacing(1)

        self.head = QLabel()
        self.head.setStyleSheet("border:none;background:transparent;")
        lay.addWidget(self.head)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.RichText)
        self.body.setOpenExternalLinks(True)
        self.body.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.body.setMaximumWidth(self.MAX_W - 20)
        lay.addWidget(self.body)
        self.setMaximumWidth(self.MAX_W)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self._stamp = datetime.now().strftime('%H:%M')
        self._raw = str(text)
        self.retheme()

    def retheme(self):
        p = pal()
        if self.kind == "you":
            who, who_col = "YOU", p["accent"]
            frame = (f"QFrame{{background:{p['bubble_you_bg']};"
                     f"border:1px solid {p['bubble_you_border']};"
                     f"border-radius:12px;}}")
        elif self.kind == "mind":
            who, who_col = "JARVIS · MIND", "#c084fc"
            frame = (f"QFrame{{background:{p['bubble_ai_bg']};"
                     f"border:1px solid #7c5cbf55;border-radius:12px;}}")
        else:
            who, who_col = "JARVIS", p["accent"]
            frame = (f"QFrame{{background:{p['bubble_ai_bg']};"
                     f"border:1px solid {p['line']};border-radius:12px;}}")
        self.setStyleSheet(frame)
        self.head.setText(f"{who}   ·   {self._stamp}")
        self.head.setStyleSheet(
            f"color:{who_col};font-size:9px;font-weight:700;"
            f"letter-spacing:2px;border:none;background:transparent;")
        self.body.setText(_md_to_html(self._raw))
        self.body.setStyleSheet(
            f"color:{p['text']};font-size:12px;border:none;"
            f"background:transparent;")


class ChatInput(QPlainTextEdit):
    """Multi-line composer that behaves like a modern chat box:
       Enter sends · Shift+Enter = new line · grows as you type ·
       Ctrl+V pastes PICTURES and FILES straight in as attachments."""

    submitted   = Signal()
    pastedFiles = Signal(list)     # [file paths]

    MIN_H, MAX_LINES = 42, 5

    def __init__(self):
        super().__init__()
        self.setPlaceholderText("Message JARVIS — or drop files here…")
        self.setAcceptDrops(False)          # Console handles drops itself
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.setFixedHeight(self.MIN_H)
        self.textChanged.connect(self._autosize)

    # Enter = send, Shift+Enter = newline
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) \
                and not (event.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def _autosize(self):
        lines = min(self.MAX_LINES, max(1, self.document().blockCount()))
        self.setFixedHeight(max(self.MIN_H, 26 + lines * 18))
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if self.document().blockCount()
            > self.MAX_LINES else Qt.ScrollBarAlwaysOff)

    # Ctrl+V with an image or copied files → attachment, not text
    def insertFromMimeData(self, source):
        try:
            if source.hasImage():
                from PySide6.QtGui import QImage
                img = QImage(source.imageData())
                if not img.isNull():
                    import config as _cfg
                    d = _cfg.MEMORY_DIR / "pasted"
                    d.mkdir(parents=True, exist_ok=True)
                    path = str(d / f"pasted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    img.save(path, "PNG")
                    self.pastedFiles.emit([path])
                    return
            if source.hasUrls():
                paths = [u.toLocalFile() for u in source.urls()
                         if u.toLocalFile() and os.path.isfile(u.toLocalFile())]
                if paths:
                    self.pastedFiles.emit(paths)
                    return
        except Exception as e:
            print(f"[Console] paste failed: {e}")
        super().insertFromMimeData(source)


class Console(QWidget):

    commandSubmitted = Signal(str)
    filesSubmitted   = Signal(str, list)   # text, [file paths]
    muteClicked      = Signal()            # speaker button pressed
    stopClicked      = Signal()            # stop-speaking button pressed
    restoreClicked   = Signal()            # mini mode → back to full JARVIS

    def __init__(self):
        super().__init__()
        self._full_width = 400
        self.setFixedWidth(self._full_width)
        self.attachments = []
        self.collapsed = False
        self.transcript = []          # (time, who, text) — for copy-all
        self._receipt_chip  = None    # active tool-receipt chip (merging)
        self._receipt_names = []
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

        # mini-mode restore — only visible while JARVIS is shrunk
        self.mini_btn = QPushButton("⛶")
        self.mini_btn.setFixedSize(24, 24)
        self.mini_btn.setCursor(Qt.PointingHandCursor)
        self.mini_btn.setToolTip("Back to the full JARVIS interface")
        self.mini_btn.setStyleSheet(
            f"QPushButton{{background:#0d1e2e;border:1px solid {CYAN}88;"
            f"border-radius:6px;color:{CYAN};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid {CYAN};background:#12324a;}}")
        self.mini_btn.clicked.connect(self.restoreClicked.emit)
        self.mini_btn.hide()
        title_row.addWidget(self.mini_btn)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(24, 24)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Stop speaking NOW (voice stays on for next reply)")
        self.stop_btn.setStyleSheet(
            f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
            f"border-radius:6px;color:{DIM};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid #ff5566;color:#ff5566;}}")
        self.stop_btn.clicked.connect(self.stopClicked.emit)
        title_row.addWidget(self.stop_btn)

        self.mute_btn = QPushButton("🔊")
        self.mute_btn.setFixedSize(24, 24)
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("Mute / unmute JARVIS's voice entirely")
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
        self.feed.setSpacing(5)
        self.feed.setContentsMargins(0, 0, 6, 0)
        self.feed.addStretch()
        self.scroll.setWidget(feed_holder)
        root.addWidget(self.scroll, 1)
        # smooth auto-scroll to newest instead of an instant jump
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        self._scroll_anim = QPropertyAnimation(
            self.scroll.verticalScrollBar(), b"value")
        self._scroll_anim.setDuration(280)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            self._smooth_to_bottom)

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

        # composer — multi-line, paste-aware
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = ChatInput()
        self.input.submitted.connect(self.submit)
        self.input.pastedFiles.connect(self._attach_files)
        self.input.setStyleSheet(
            f"QPlainTextEdit{{background:#08111c;border:1px dashed {CYAN}44;"
            f"border-radius:10px;padding:8px;color:{ICE};"
            f"font-size:12px;}}"
            f"QPlainTextEdit:focus{{border:1px solid {CYAN};}}")
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

    def _smooth_to_bottom(self, _min, mx):
        bar = self.scroll.verticalScrollBar()
        # only animate if we're already near the bottom (don't yank the
        # view down while Shaun is scrolled up reading history)
        if bar.value() >= bar.maximum() - 240 or bar.value() == 0:
            self._scroll_anim.stop()
            self._scroll_anim.setStartValue(bar.value())
            self._scroll_anim.setEndValue(mx)
            self._scroll_anim.start()

    # ── theming ─────────────────────────────────
    def retheme(self):
        p = pal()
        panel_bg = ("rgba(255,255,255,0.92)" if p["name"] == "light"
                    else "rgba(10,20,32,0.88)")
        self.setStyleSheet(
            f"Console{{background:{panel_bg};border:1px solid {p['line']};"
            f"border-radius:12px;}}"
            f"QWidget{{background:transparent;border:none;}}")
        self.title.setStyleSheet(
            f"color:{p['accent']};font-size:12px;font-weight:700;"
            f"letter-spacing:3px;border:none;")
        btn = (f"QPushButton{{background:{p['panel2']};border:1px solid "
               f"{p['line']};border-radius:6px;color:{p['dim']};"
               f"font-size:11px;}}"
               f"QPushButton:hover{{border:1px solid {p['accent']};"
               f"color:{p['accent']};}}")
        for b in (self.copy_btn, self.collapse_btn, self.mute_btn):
            b.setStyleSheet(btn)
        self.stop_btn.setStyleSheet(
            f"QPushButton{{background:{p['panel2']};border:1px solid "
            f"{p['line']};border-radius:6px;color:{p['dim']};font-size:11px;}}"
            f"QPushButton:hover{{border:1px solid #ff5566;color:#ff5566;}}")
        self.input.setStyleSheet(
            f"QPlainTextEdit{{background:{p['panel2']};border:1px dashed "
            f"{p['accent']}66;border-radius:10px;padding:8px;"
            f"color:{p['text']};font-size:12px;}}"
            f"QPlainTextEdit:focus{{border:1px solid {p['accent']};}}")
        self._send_btn.setStyleSheet(
            f"QPushButton{{background:{p['accent']};color:white;border:none;"
            f"border-radius:10px;font-size:14px;font-weight:700;}}"
            f"QPushButton:hover{{background:{p['accent']}cc;}}")
        # restyle every bubble already in the feed
        for i in range(self.feed.count()):
            item = self.feed.itemAt(i)
            w = item.widget() if item else None
            if w is None and item and item.layout():
                for j in range(item.layout().count()):
                    inner = item.layout().itemAt(j).widget()
                    if isinstance(inner, Bubble):
                        inner.retheme()
            if isinstance(w, Bubble):
                w.retheme()

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
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
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
        # internal plumbing — mini-tab payloads and window-mode markers
        # must NEVER hit the chat
        if text.startswith("→ show_info:") or text.startswith("→ mini_mode:"):
            return
        self._log("SYSTEM", text)
        # tool receipts: "→ tool_name" from the brain's planning loop.
        # Consecutive receipts MERGE into one compact line instead of
        # raining separate chips that push the conversation apart.
        if text.startswith("→ "):
            name = text[2:].strip()
            # defensive: never show raw payloads in a receipt
            if "{" in name:
                name = name.split("{", 1)[0].rstrip(": ")
            name = name[:60]
            if self._receipt_chip is not None and len(self._receipt_names) < 6:
                self._receipt_names.append(name)
                self._receipt_chip.setText("✓ " + " · ".join(self._receipt_names))
                return
            self._receipt_names = [name]
            chip = QLabel(f"✓ {name}")
            chip.setWordWrap(True)
            chip.setMaximumWidth(int(self._full_width * 0.9))
            chip.setStyleSheet(
                f"color:{GREEN};font-size:10px;border:1px dashed {LINE};"
                f"border-radius:7px;padding:3px 10px;background:transparent;")
            self._receipt_chip = chip
            self._add(chip, "left")
            return
        self._receipt_chip = None   # anything else breaks the merge run
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
        self._receipt_chip = None
        self._log("YOU", text)
        self._add(Bubble(str(text), "you"), "right")

    def append_agent(self, role, text):
        self._receipt_chip = None
        self._log(role.upper(), text)
        self._add(Bubble(f"[{role}] {text}", "jarvis"), "left")

    def append_response(self, text):
        self._receipt_chip = None
        text = str(text)
        self._log("JARVIS", text)
        kind = "mind" if text.startswith("[Mind]") else "jarvis"
        self._add(Bubble(text, kind), "left")

    def _attach_files(self, paths):
        """Pasted pictures / copied files land here as attachments."""
        for p in paths:
            if p not in self.attachments:
                self.attachments.append(p)
        self._refresh_chips()

    # ── submit ──────────────────────────────────
    def submit(self):
        text = self.input.toPlainText().strip()
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
