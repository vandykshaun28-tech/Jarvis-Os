from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextBrowser,
    QLineEdit,
    QLabel,
    QPushButton,
)

from PySide6.QtCore import Signal, Qt


ROLE_COLORS = {
    "SYSTEM": "#7ba7c2",
    "YOU": "#22d3ee",
    "CLAUDE": "#2ecc71",
    "INTERNET": "#3b82f6",
    "MEMORY": "#22c55e",
    "VOICE": "#c084fc",
    "JARVIS": "#22d3ee",
}


class Console(QWidget):

    commandSubmitted = Signal(str)

    def __init__(self):

        super().__init__()

        self.setFixedWidth(400)

        self.build_ui()

    # --------------------------------------------------

    def build_ui(self):

        layout = QVBoxLayout()

        layout.setContentsMargins(14, 12, 14, 14)

        layout.setSpacing(10)

        self.setLayout(layout)

        # ------------------------------------------------
        # Title bar
        # ------------------------------------------------

        title_row = QHBoxLayout()

        title_row.setSpacing(6)

        title = QLabel("JARVIS CONSOLE")

        title.setObjectName("title")

        title_row.addWidget(title)

        title_row.addStretch()

        for glyph in ("\u2212", "\u2b1a", "\u2715"):

            btn = QPushButton(glyph)

            btn.setFixedSize(22, 22)

            btn.setCursor(Qt.PointingHandCursor)

            btn.setObjectName("winbtn")

            title_row.addWidget(btn)

        layout.addLayout(title_row)

        # ------------------------------------------------
        # Log area
        # ------------------------------------------------

        self.log = QTextBrowser()

        self.log.setOpenExternalLinks(False)

        layout.addWidget(self.log, 1)

        # ------------------------------------------------
        # Input
        # ------------------------------------------------

        self.input = QLineEdit()

        self.input.setPlaceholderText("Type a command and press Enter...")

        self.input.returnPressed.connect(self.submit)

        layout.addWidget(self.input)

        self.append_system("JARVIS Console Online.")

        self.append_system("Ready.")

        self.setStyleSheet("""

        QWidget{

            background:#0a1420;

            border:1px solid #12324a;

            border-radius:12px;

        }

        #title{

            border:none;

            color:white;

            font-size:15px;

            font-weight:bold;

        }

        #winbtn{

            background:#0d1e2e;

            border:1px solid #12324a;

            border-radius:5px;

            color:#7ba7c2;

            font-size:10px;

            padding:0px;

        }

        #winbtn:hover{

            border:1px solid #22d3ee;

            color:#22d3ee;

        }

        QTextBrowser{

            background:#0a1420;

            border:none;

            color:#c7e3f5;

            font-family:Consolas;

            font-size:12px;

        }

        QTextBrowser QWidget{

            background:#0a1420;

        }

        QLineEdit{

            background:#08111c;

            border:1px solid #12324a;

            border-radius:8px;

            padding:10px;

            color:white;

            font-family:Consolas;

            font-size:12px;

        }

        QLineEdit:focus{

            border:1px solid #22d3ee;

        }

        """)

    # --------------------------------------------------

    def _time(self):

        return datetime.now().strftime("%H:%M:%S")

    def _scroll_bottom(self):

        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum()
        )

    # --------------------------------------------------

    def append_system(self, text):

        color = ROLE_COLORS["SYSTEM"]

        self.log.append(

            f"<span style='color:#4d6579'>{self._time()}</span>&nbsp;&nbsp;"
            f"<span style='color:{color};font-weight:bold;'>SYSTEM</span>&nbsp;&nbsp;"
            f"<span style='color:#c7e3f5'>{text}</span>"

        )

        self._scroll_bottom()

    def append_user(self, text):

        color = ROLE_COLORS["YOU"]

        self.log.append("<br>")

        self.log.append(

            f"<span style='color:#4d6579'>{self._time()}</span>&nbsp;&nbsp;"
            f"<span style='color:{color};font-weight:bold;'>YOU</span>&nbsp;&nbsp;"
            f"<span style='color:#e8f6ff'>{text}</span>"

        )

        self._scroll_bottom()

    def append_agent(self, role, text):

        color = ROLE_COLORS.get(role.upper(), "#7ba7c2")

        self.log.append(

            f"<span style='color:#4d6579'>{self._time()}</span>&nbsp;&nbsp;"
            f"<span style='color:{color};font-weight:bold;'>{role.upper()}</span>&nbsp;&nbsp;"
            f"<span style='color:#c7e3f5'>{text}</span>"

        )

        self._scroll_bottom()

    def append_response(self, text):

        color = ROLE_COLORS["JARVIS"]

        self.log.append("<br>")

        self.log.append(

            f"<span style='color:{color};font-weight:bold;font-size:13px;'>JARVIS</span>&nbsp;&nbsp;"
            f"<span style='color:#e8f6ff'>{text}</span>"

        )

        self.log.append("<br>")

        self._scroll_bottom()

    # --------------------------------------------------

    def submit(self):

        text = self.input.text().strip()

        if not text:

            return

        self.append_user(text)

        self.commandSubmitted.emit(text)

        self.input.clear()

    def set_status(self, text):

        self.append_system(text)

    def append_system_text(self, text):

        self.append_system(text)
