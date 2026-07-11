import os

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon


class SidebarButton(QPushButton):

    def __init__(self, icon, text, active=False):

        super().__init__()

        self.icon = icon
        self.text_value = text

        self.expanded = True

        self._active = active

        self.setCursor(Qt.PointingHandCursor)

        self.setMinimumHeight(46)

        self.setCheckable(True)

        self.setChecked(active)

        # icon may be an emoji/glyph OR a path to an image file
        # (e.g. the Shopify logo) — image paths become real QIcons.
        self._is_image = (isinstance(icon, str)
                          and icon.lower().endswith((".png", ".svg", ".ico"))
                          and os.path.exists(icon))
        if self._is_image:
            self.setIcon(QIcon(icon))
            self.setIconSize(QSize(20, 20))
            self.setText(f"  {text}")
        else:
            self.setText(f"  {icon}   {text}")

        self.setObjectName("sidebarButton")

        self._apply_style()

    # --------------------------------------------------

    def _apply_style(self):
        try:
            from ui.styles.theme_manager import pal
            p = pal()
        except Exception:
            p = {"accent": "#22d3ee", "text2": "#8fb7cf",
                 "panel2": "#0f2436", "line": "#1e5c86",
                 "text": "white", "name": "dark"}
        checked_bg = ("rgba(11,127,163,30)" if p["name"] == "light"
                      else "rgba(34,211,238,40)")
        self.setStyleSheet(f"""
        QPushButton{{
            background:transparent;
            border:none;
            border-radius:9px;
            text-align:left;
            padding-left:6px;
            color:{p['text2']};
            font-size:14px;
            font-weight:500;
        }}
        QPushButton:hover{{
            background:{p['panel2']};
            color:{p['text']};
        }}
        QPushButton:checked{{
            background:qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {checked_bg},
                stop:1 transparent
            );
            border:1px solid {p['line']};
            border-left:3px solid {p['accent']};
            color:{p['text']};
            font-weight:600;
        }}
        """)

    def retheme(self):
        self._apply_style()

    # --------------------------------------------------

    def collapse(self):

        self.expanded = False

        if self._is_image:
            self.setText("")
        else:
            self.setText(f"  {self.icon}")

    def expand(self):

        self.expanded = True

        if self._is_image:
            self.setText(f"  {self.text_value}")
        else:
            self.setText(f"  {self.icon}   {self.text_value}")
