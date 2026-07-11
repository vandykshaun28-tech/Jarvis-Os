from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
)

from PySide6.QtCore import Qt


class StatusCard(QFrame):

    def __init__(self, title, value="", icon="●", color="#22d3ee"):

        super().__init__()

        self.color = color

        self.setFixedHeight(56)

        self.setMinimumWidth(118)

        root = QHBoxLayout()

        root.setContentsMargins(12, 6, 16, 6)

        root.setSpacing(10)

        self.setLayout(root)

        # ----------------------------------------
        # Icon chip
        # ----------------------------------------

        self.icon_label = QLabel(icon)

        self.icon_label.setFixedSize(34, 34)

        self.icon_label.setAlignment(Qt.AlignCenter)

        self.icon_label.setObjectName("icon_chip")

        root.addWidget(self.icon_label)

        # ----------------------------------------
        # Text block
        # ----------------------------------------

        text_col = QVBoxLayout()

        text_col.setSpacing(0)

        text_col.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel(title)

        self.title.setObjectName("title")

        self.value = QLabel(value)

        self.value.setObjectName("value")

        text_col.addWidget(self.title)

        text_col.addWidget(self.value)

        root.addLayout(text_col)

        self.setStyleSheet(f"""

        QFrame{{

            background:#0a1420;

            border:1px solid #12324a;

            border-radius:12px;

        }}

        QLabel{{

            border:none;

            background:transparent;

        }}

        #icon_chip{{

            background:rgba({self._rgba(color, 28)});

            border:1px solid {color};

            border-radius:17px;

            font-size:15px;

            color:{color};

        }}

        #title{{

            color:#7ba7c2;

            font-size:10px;

            font-weight:600;

        }}

        #value{{

            color:white;

            font-size:15px;

            font-weight:bold;

        }}

        """)

    # --------------------------------------------------

    def retheme(self):
        from ui.styles.theme_manager import pal
        p = pal()
        self.setStyleSheet(f"""
        QFrame{{
            background:{p['panel']};
            border:1px solid {p['line']};
            border-radius:12px;
        }}
        QLabel{{ border:none; background:transparent; }}
        #icon_chip{{
            background:rgba({self._rgba(self.color, 28)});
            border:1px solid {self.color};
            border-radius:17px;
            font-size:15px;
            color:{self.color};
        }}
        #title{{ color:{p['text2']}; font-size:10px; font-weight:600; }}
        #value{{ color:{p['text']}; font-size:15px; font-weight:bold; }}
        """)

    # --------------------------------------------------

    @staticmethod
    def _rgba(hex_color, alpha):

        hex_color = hex_color.lstrip("#")

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        return f"{r},{g},{b},{alpha}"
