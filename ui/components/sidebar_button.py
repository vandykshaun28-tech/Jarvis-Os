from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


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

        self.setText(f"  {icon}   {text}")

        self.setObjectName("sidebarButton")

        self._apply_style()

    # --------------------------------------------------

    def _apply_style(self):

        self.setStyleSheet("""

        QPushButton{

            background:transparent;

            border:none;

            border-radius:9px;

            text-align:left;

            padding-left:6px;

            color:#8fb7cf;

            font-size:14px;

            font-weight:500;

        }

        QPushButton:hover{

            background:#0f2436;

            color:white;

        }

        QPushButton:checked{

            background:qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(34,211,238,40),
                stop:1 rgba(34,211,238,6)
            );

            border:1px solid #1e5c86;

            border-left:3px solid #22d3ee;

            color:white;

            font-weight:600;

        }

        """)

    # --------------------------------------------------

    def collapse(self):

        self.expanded = False

        self.setText(f"  {self.icon}")

    def expand(self):

        self.expanded = True

        self.setText(f"  {self.icon}   {self.text_value}")
