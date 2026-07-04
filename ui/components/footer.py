from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout


class FooterItem(QWidget):

    def __init__(self, icon, label, value, value_color="#2ecc71"):

        super().__init__()

        layout = QHBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)

        layout.setSpacing(6)

        self.setLayout(layout)

        icon_lbl = QLabel(icon)

        icon_lbl.setStyleSheet("border:none; font-size:12px; color:#7ba7c2;")

        layout.addWidget(icon_lbl)

        text_lbl = QLabel(label)

        text_lbl.setStyleSheet("border:none; font-size:11px; color:#8fb7cf;")

        layout.addWidget(text_lbl)

        self.value_lbl = QLabel(value)

        self.value_lbl.setStyleSheet(
            f"border:none; font-size:11px; font-weight:600; color:{value_color};"
        )

        layout.addWidget(self.value_lbl)


class Footer(QWidget):

    def __init__(self):

        super().__init__()

        self.setFixedHeight(40)

        layout = QHBoxLayout()

        layout.setContentsMargins(20, 0, 20, 0)

        layout.setSpacing(28)

        self.setLayout(layout)

        self.status_item = FooterItem(
            "\U0001f4ca", "System Status:", "Optimal", "#2ecc71"
        )

        self.temp_item = FooterItem(
            "\U0001f321", "AI Core Temperature:", "42\u00b0C", "#2ecc71"
        )

        self.network_item = FooterItem(
            "\U0001f4e1", "Network:", "Stable", "#2ecc71"
        )

        layout.addWidget(self.status_item)

        layout.addWidget(self.temp_item)

        layout.addWidget(self.network_item)

        layout.addStretch()

        copyright_lbl = QLabel("\u00a9 2026 JARVIS OS v20")

        copyright_lbl.setStyleSheet(
            "border:none; font-size:11px; color:#22d3ee;"
        )

        layout.addWidget(copyright_lbl)

        self.setStyleSheet("""

        QWidget{

            background:rgba(10,20,32,0.88);

            border:1px solid #12324a;

            border-radius:10px;

        }

        """)
