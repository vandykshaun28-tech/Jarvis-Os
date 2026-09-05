from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QButtonGroup,
)

from PySide6.QtCore import Qt

from ui.components.sidebar_button import SidebarButton


def _shopify_icon():
    """Path to the real Shopify logo if it exists, else the old glyph."""
    try:
        import config
        p = config.ROOT_DIR / "assets" / "shopify_logo.png"
        if p.exists():
            return str(p)
    except Exception:
        pass
    return "\U0001f6d2"


class SidebarStatusRow(QWidget):

    def __init__(self, label, value, color="#2ecc71"):

        super().__init__()

        layout = QHBoxLayout()

        layout.setContentsMargins(4, 3, 4, 3)

        layout.setSpacing(8)

        self.setLayout(layout)

        dot = QLabel("\u25cf")

        dot.setStyleSheet(f"color:{color}; font-size:9px; border:none;")

        layout.addWidget(dot)

        name = QLabel(label)

        name.setStyleSheet("color:#c7e3f5; font-size:12px; border:none;")

        layout.addWidget(name)

        layout.addStretch()

        val = QLabel(value)

        val.setStyleSheet(f"color:{color}; font-size:11px; font-weight:600; border:none;")

        layout.addWidget(val)


class Sidebar(QWidget):

    def __init__(self):

        super().__init__()

        self.expanded = True
        self.hidden = False

        self.buttons = []

        self.setFixedWidth(256)

        self.build_ui()

    def build_ui(self):

        root = QVBoxLayout()

        root.setContentsMargins(14, 14, 14, 14)

        root.setSpacing(10)

        self.setLayout(root)

        # ------------------------------------------------
        # Collapse toggle
        # ------------------------------------------------

        toggle_row = QHBoxLayout()

        toggle_row.addStretch()

        self.toggle = QPushButton("\u00ab")

        self.toggle.setFixedSize(28, 28)

        self.toggle.setCursor(Qt.PointingHandCursor)

        self.toggle.clicked.connect(
            self.toggle_sidebar
        )

        self.toggle.setStyleSheet("""

        QPushButton{

            background:rgba(10,20,32,0.88);

            border:1px solid #12324a;

            border-radius:14px;

            color:#7ba7c2;

            font-size:13px;

        }

        QPushButton:hover{

            border:1px solid #22d3ee;

            color:#22d3ee;

        }

        """)

        toggle_row.addWidget(self.toggle)

        root.addLayout(toggle_row)

        # ------------------------------------------------
        # Nav list
        # ------------------------------------------------

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(QFrame.NoFrame)

        scroll.setStyleSheet("background:transparent; border:none;")

        scroll.viewport().setStyleSheet("background:transparent;")

        root.addWidget(scroll, 1)

        container = QWidget()

        container.setStyleSheet("background:transparent;")

        scroll.setWidget(container)

        layout = QVBoxLayout()

        layout.setSpacing(4)

        layout.setContentsMargins(0, 0, 0, 0)

        container.setLayout(layout)

        pages = [

            ("\U0001f3e0", "Dashboard"),

            ("\U0001f9be", "AI Agents"),

            ("\U0001f9ea", "Research"),

            ("\U0001f310", "Internet"),

            ("\U0001f4c8", "Trading"),

            ("\u2699", "PLC"),

            ("\U0001f697", "Vehicle"),

            (_shopify_icon(), "Shopify"),

            ("\u2699", "Settings"),

        ]

        self.group = QButtonGroup(self)

        self.group.setExclusive(True)

        for i, (icon, name) in enumerate(pages):

            button = SidebarButton(icon, name, active=(i == 0))

            self.buttons.append(button)

            self.group.addButton(button)

            layout.addWidget(button)

        layout.addStretch()

        # ------------------------------------------------
        # System panel
        # ------------------------------------------------

        self.divider = QFrame()

        self.divider.setFrameShape(QFrame.HLine)

        self.divider.setStyleSheet("background:#12324a; max-height:1px; border:none;")

        root.addWidget(self.divider)

        self.sys_label = QLabel("SYSTEM")

        self.sys_label.setStyleSheet(
            "color:#5a8bb0; font-size:10px; font-weight:700; "
            "letter-spacing:2px; border:none; padding-top:2px;"
        )

        root.addWidget(self.sys_label)

        self.claude_row = SidebarStatusRow("Claude", "Online", "#2ecc71")

        self.internet_row = SidebarStatusRow("Internet", "Online", "#2ecc71")

        self.voice_row = SidebarStatusRow("Voice", "Online", "#2ecc71")

        self.memory_row = SidebarStatusRow("Memory", "Active", "#2ecc71")

        self.status_rows = [
            self.claude_row,
            self.internet_row,
            self.voice_row,
            self.memory_row,
        ]

        for row in self.status_rows:

            root.addWidget(row)

        # ------------------------------------------------
        # Footer status text
        # ------------------------------------------------

        self.footer_label = QLabel("ALLISON OS \u2022 Ready")

        self.footer_label.setStyleSheet(
            "color:#22d3ee; font-size:11px; font-weight:600; "
            "border:none; padding-top:4px;"
        )

        root.addWidget(self.footer_label)

        self.setStyleSheet("""

        QWidget{

            background:#0a1420;

            border:1px solid #12324a;

            border-radius:12px;

            color:#22d3ee;

        }

        QScrollArea{

            border:none;

            background:transparent;

        }

        QScrollBar:vertical{

            background:transparent;

            width:5px;

            margin:0px;

        }

        QScrollBar::handle:vertical{

            background:#12324a;

            border-radius:2px;

            min-height:30px;

        }

        QScrollBar::handle:vertical:hover{

            background:#22d3ee;

        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical{

            height:0px;

        }

        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical{

            background:transparent;

        }

        """)

    # --------------------------------------------------

    def retheme(self):
        from ui.styles.theme_manager import pal
        p = pal()
        self.setStyleSheet(f"""
        QWidget{{
            background:{p['panel']};
            border:1px solid {p['line']};
            border-radius:12px;
            color:{p['accent']};
        }}
        QScrollArea{{ border:none; background:transparent; }}
        QScrollBar:vertical{{ background:transparent; width:5px; margin:0; }}
        QScrollBar::handle:vertical{{ background:{p['line']};
            border-radius:2px; min-height:30px; }}
        QScrollBar::handle:vertical:hover{{ background:{p['accent']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{
            height:0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical{{
            background:transparent; }}
        """)
        self.toggle.setStyleSheet(
            f"QPushButton{{background:{p['panel']};border:1px solid "
            f"{p['line']};border-radius:14px;color:{p['text2']};"
            f"font-size:13px;}}"
            f"QPushButton:hover{{border:1px solid {p['accent']};"
            f"color:{p['accent']};}}")
        self.sys_label.setStyleSheet(
            f"color:{p['dim']};font-size:10px;font-weight:700;"
            f"letter-spacing:2px;border:none;padding-top:2px;")
        self.footer_label.setStyleSheet(
            f"color:{p['accent']};font-size:11px;font-weight:600;"
            f"border:none;padding-top:4px;")
        for b in self.buttons:
            b.retheme()

    # --------------------------------------------------

    # ── HIDE / REVEAL ────────────────────────────────────────────────
    # The old sidebar only ever collapsed to a 76px icon rail, so it was
    # always taking up screen. Shaun wants it GONE until he asks for it,
    # with the HUD clean in between. Width 0 is a genuine hide — the
    # reveal handle lives in main_window because a button inside a
    # zero-width widget cannot be clicked.

    HIDDEN_W = 0
    RAIL_W = 76
    FULL_W = 256

    def _animate_to(self, width, ms=180):
        """Slide to a width. Falls back to an instant set if the
        animation classes are unavailable for any reason."""
        try:
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve
            anim = QPropertyAnimation(self, b"maximumWidth", self)
            anim.setDuration(ms)
            anim.setStartValue(self.width())
            anim.setEndValue(width)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.setMinimumWidth(0)
            anim.finished.connect(lambda: self.setFixedWidth(width))
            anim.start()
            self._anim = anim            # keep a ref or it is GC'd mid-flight
        except Exception:
            self.setFixedWidth(width)

    def hide_sidebar(self, animate=True):
        """Fully out of the way."""
        self.hidden = True
        if animate:
            self._animate_to(self.HIDDEN_W)
        else:
            self.setFixedWidth(self.HIDDEN_W)

    def reveal_sidebar(self, full=True, animate=True):
        """Bring it back, expanded by default so he can read it."""
        self.hidden = False
        self.expanded = full
        for b in self.buttons:
            b.expand() if full else b.collapse()
        for w in (self.footer_label, self.divider, self.sys_label,
                  *self.status_rows):
            w.show() if full else w.hide()
        self.toggle.setText("\u00ab" if full else "\u00bb")
        target = self.FULL_W if full else self.RAIL_W
        if animate:
            self._animate_to(target)
        else:
            self.setFixedWidth(target)

    def toggle_hidden(self):
        """What the edge handle calls."""
        if getattr(self, "hidden", False):
            self.reveal_sidebar(full=True)
        else:
            self.hide_sidebar()
        return not self.hidden

    def toggle_sidebar(self):

        if self.expanded:

            self.setFixedWidth(76)

            self.toggle.setText("\u00bb")

            for b in self.buttons:

                b.collapse()

            self.footer_label.hide()

            self.divider.hide()

            self.sys_label.hide()

            for row in self.status_rows:

                row.hide()

        else:

            self.setFixedWidth(256)

            self.toggle.setText("\u00ab")

            for b in self.buttons:

                b.expand()

            self.footer_label.show()

            self.divider.show()

            self.sys_label.show()

            for row in self.status_rows:

                row.show()

        self.expanded = not self.expanded
