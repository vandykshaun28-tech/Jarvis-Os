"""
Settings page — controls that actually DO things, persisted across
restarts via core/settings.py (memory/settings.json).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea,
)
from PySide6.QtCore import Qt

from core import settings


CYAN, LINE, DIM = "#22d3ee", "#12324a", "#7ba7c2"


def _section(title):
    box = QFrame()
    box.setStyleSheet(
        f"QFrame{{background:#0a1420;border:1px solid {LINE};"
        f"border-radius:12px;}}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setStyleSheet(f"color:{CYAN};font-size:11px;font-weight:700;"
                    f"letter-spacing:2px;border:none;")
    lay.addWidget(t)
    return box, lay


class ToggleRow(QWidget):
    """Label + description + ON/OFF pill buttons."""

    def __init__(self, label, desc, options, current, on_change):
        super().__init__()
        self.on_change = on_change
        self.buttons = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        name = QLabel(label)
        name.setStyleSheet("color:#e8f6ff;font-size:13px;font-weight:600;"
                           "border:none;background:transparent;")
        d = QLabel(desc)
        d.setStyleSheet(f"color:{DIM};font-size:10px;border:none;"
                        "background:transparent;")
        d.setWordWrap(True)
        text_col.addWidget(name)
        text_col.addWidget(d)
        lay.addLayout(text_col, 1)

        for value, caption in options:
            b = QPushButton(caption)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            b.setMinimumWidth(72)
            b.setStyleSheet(
                f"QPushButton{{background:#0d1e2e;border:1px solid {LINE};"
                f"border-radius:8px;color:{DIM};font-size:11px;"
                f"font-weight:600;padding:0 12px;}}"
                f"QPushButton:hover{{border:1px solid {CYAN};}}"
                f"QPushButton:checked{{background:rgba(34,211,238,30);"
                f"border:1px solid {CYAN};color:white;}}")
            b.clicked.connect(lambda _=False, v=value: self._pick(v))
            self.buttons[value] = b
            lay.addWidget(b)
        self.set_value(current)

    def _pick(self, value):
        self.set_value(value)
        try:
            self.on_change(value)
        except Exception as e:
            print(f"[Settings] change failed: {e}")

    def set_value(self, value):
        for v, b in self.buttons.items():
            b.setChecked(v == value)


class SwatchRow(QWidget):
    """A row of clickable colour swatches for picking the accent."""

    def __init__(self, accents: dict, current: str, on_change):
        super().__init__()
        self.on_change = on_change
        self.swatches = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(10)

        label = QLabel("Accent colour")
        label.setStyleSheet("color:#e8f6ff;font-size:13px;font-weight:600;"
                            "border:none;background:transparent;")
        lay.addWidget(label, 1)

        for name, hexc in accents.items():
            b = QPushButton()
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(30, 30)
            b.setToolTip(name)
            b.clicked.connect(lambda _=False, n=name: self._pick(n))
            self.swatches[name] = (b, hexc)
            lay.addWidget(b)
        self.set_value(current)

    def _style(self, hexc, selected):
        border = "3px solid white" if selected else f"2px solid {hexc}"
        return (f"QPushButton{{background:{hexc};border:{border};"
                f"border-radius:15px;}}"
                f"QPushButton:hover{{border:3px solid #e8f6ff;}}")

    def _pick(self, name):
        self.set_value(name)
        try:
            self.on_change(name)
        except Exception as e:
            print(f"[Settings] accent change failed: {e}")

    def set_value(self, name):
        for n, (b, hexc) in self.swatches.items():
            b.setChecked(n == name)
            b.setStyleSheet(self._style(hexc, n == name))


class SettingsPage(QWidget):
    """window_ref: the MainWindow (for theme + controller access)."""

    def __init__(self, window_ref=None):
        super().__init__()
        self.window_ref = window_ref
        self.setStyleSheet("background:transparent;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none;")
        scroll.viewport().setStyleSheet("background:transparent;")
        outer.addWidget(scroll)

        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        scroll.setWidget(holder)
        root = QVBoxLayout(holder)
        root.setContentsMargins(0, 0, 8, 0)
        root.setSpacing(12)

        header = QLabel("SETTINGS")
        header.setStyleSheet("color:#e8f6ff;font-size:16px;font-weight:700;"
                             "letter-spacing:3px;border:none;")
        root.addWidget(header)

        # ── Appearance ──────────────────────────
        box, lay = _section("APPEARANCE")
        lay.addWidget(ToggleRow(
            "Theme", "Switches the whole interface between dark and "
            "light instantly.",
            [("dark", "Dark"), ("light", "Light")],
            settings.get("theme"), self._set_theme))
        from ui.styles.theme_manager import ACCENTS
        lay.addWidget(SwatchRow(ACCENTS, settings.get("accent"),
                                self._set_accent))
        root.addWidget(box)

        # ── Voice ───────────────────────────────
        box, lay = _section("VOICE")
        lay.addWidget(ToggleRow(
            "Spoken replies", "JARVIS reads his answers aloud.",
            [(True, "On"), (False, "Off")],
            settings.get("voice_enabled"), self._set_voice))
        lay.addWidget(ToggleRow(
            "Wake word", "Microphone listens for 'Allison'.",
            [(True, "On"), (False, "Off")],
            settings.get("wake_word_enabled"), self._set_wake))
        root.addWidget(box)

        # ── Brain ───────────────────────────────
        box, lay = _section("BRAIN")
        lay.addWidget(ToggleRow(
            "Model mode", "Auto = cheap Haiku for chat, Sonnet only for "
            "heavy work (recommended). Always Smart = Sonnet for "
            "everything (best quality, ~3-5x cost).",
            [("auto", "Auto"), ("smart", "Always Smart")],
            settings.get("brain_mode"), self._set_brain))
        root.addWidget(box)

        # ── Interface ───────────────────────────
        box, lay = _section("INTERFACE")
        lay.addWidget(ToggleRow(
            "Mini-tab pop-ups", "Information pops up in floating movable "
            "panels (Iron-Man style) as well as in the chat.",
            [(True, "On"), (False, "Off")],
            settings.get("mini_tabs"), self._set_minitabs))
        root.addWidget(box)

        note = QLabel("Changes apply immediately and are saved to "
                      "memory/settings.json.")
        note.setStyleSheet(f"color:{DIM};font-size:10px;border:none;")
        root.addWidget(note)
        root.addStretch()

    # ── handlers — every one takes effect NOW ────
    def _set_theme(self, value):
        settings.set("theme", value)
        w = self.window_ref
        if w and hasattr(w, "apply_theme"):
            w.apply_theme(value)

    def _set_accent(self, name):
        settings.set("accent", name)
        from ui.styles.theme_manager import ACCENTS, set_accent
        set_accent(ACCENTS.get(name))
        w = self.window_ref
        if w and hasattr(w, "apply_theme"):
            w.apply_theme(settings.get("theme"))   # re-push palette everywhere

    def _set_voice(self, value):
        settings.set("voice_enabled", bool(value))
        w = self.window_ref
        if w and getattr(w, "controller", None):
            w.controller.set_voice_muted(not value)

    def _set_wake(self, value):
        settings.set("wake_word_enabled", bool(value))
        w = self.window_ref
        listener = getattr(w.controller, "listener", None) if w else None
        if listener:
            try:
                listener.mute() if not value else listener.unmute()
            except Exception as e:
                print(f"[Settings] wake toggle: {e}")

    def _set_brain(self, value):
        settings.set("brain_mode", value)

    def _set_minitabs(self, value):
        settings.set("mini_tabs", bool(value))
