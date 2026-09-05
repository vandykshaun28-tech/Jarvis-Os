from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
)

from PySide6.QtCore import (
    Qt,
    QTimer,
)

from datetime import datetime

import psutil

from ui.widgets.ai_core.status_card import StatusCard


class Header(QWidget):

    def __init__(self, controller=None):

        super().__init__()

        self.controller = controller

        self.setFixedHeight(96)

        self.build_ui()

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_status
        )

        self.timer.start(1000)

        self.update_status()

    def build_ui(self):

        layout = QHBoxLayout()

        layout.setContentsMargins(18, 10, 18, 10)

        layout.setSpacing(16)

        self.setLayout(layout)

        # ------------------------------------------------
        # Logo block
        # ------------------------------------------------

        self.logo = QLabel("\u2b21")

        self.logo.setFixedSize(56, 56)

        self.logo.setAlignment(Qt.AlignCenter)

        self.logo.setObjectName("logo")

        layout.addWidget(self.logo)

        title_block = QVBoxLayout()

        title_block.setSpacing(0)

        title_block.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel("ALLISON")

        self.title.setObjectName("title")

        self.subtitle = QLabel("AI COMMAND CENTER")

        self.subtitle.setObjectName("subtitle")

        title_block.addWidget(self.title)

        title_block.addWidget(self.subtitle)

        layout.addLayout(title_block)

        layout.addStretch()

        # ------------------------------------------------
        # Status pills
        # ------------------------------------------------

        self.cpu = StatusCard("CPU", icon="\u25a6", color="#22d3ee")

        self.ram = StatusCard("RAM", icon="\u25a4", color="#22d3ee")

        self.internet = StatusCard("Internet", icon="\U0001f310", color="#3b82f6")

        self.claude = StatusCard("Claude", icon="\U0001f9e0", color="#b06bff")

        self.cost = StatusCard("Cost today", icon="\U0001f4b0", color="#facc15")
        self.cost.setToolTip("This month: $0.0000")

        self.balance = StatusCard("Balance", icon="\U0001f4b3", color="#2ecc71")
        self.balance.setToolTip(
            "Credits left, counting down from CREDIT_BALANCE_USD in "
            "config.py.\nTop up / re-sync: check console.anthropic.com → "
            "Billing and update that number.")

        self.voice = StatusCard("Voice", icon="\U0001f3a4", color="#14b8a6")

        self.memory = StatusCard("Memory", icon="\U0001f5c4", color="#22c55e")

        self.clock = StatusCard("Time", icon="\U0001f550", color="#7ba7c2")

        for card in (
            self.cpu,
            self.ram,
            self.internet,
            self.claude,
            self.cost,
            self.balance,
            self.voice,
            self.memory,
            self.clock,
        ):

            layout.addWidget(card)

        self.balance.hide()   # appears once CREDIT_BALANCE_USD is set

        self.setStyleSheet("""

        QWidget{

            background:rgba(10,20,32,0.88);

            border:1px solid #12324a;

            border-radius:12px;

        }

        #logo{

            background:qradialgradient(
                cx:0.5, cy:0.5, radius:0.8,
                fx:0.5, fy:0.5,
                stop:0 #123049,
                stop:1 #05070d
            );

            border:2px solid #22d3ee;

            border-radius:28px;

            font-size:22px;

            color:#22d3ee;

        }

        #title{

            font-size:22px;

            font-weight:bold;

            color:white;

            border:none;

        }

        #subtitle{

            font-size:10px;

            font-weight:600;

            color:#5a8bb0;

            letter-spacing:2px;

            border:none;

        }

        """)

    def retheme(self):
        from ui.styles.theme_manager import pal
        p = pal()
        panel_bg = ("rgba(255,255,255,0.92)" if p["name"] == "light"
                    else "rgba(10,20,32,0.88)")
        title_col = p["text"] if p["name"] == "light" else "white"
        self.setStyleSheet(f"""
        QWidget{{
            background:{panel_bg};
            border:1px solid {p['line']};
            border-radius:12px;
        }}
        #logo{{
            background:qradialgradient(
                cx:0.5, cy:0.5, radius:0.8, fx:0.5, fy:0.5,
                stop:0 {p['panel2']}, stop:1 {p['panel']});
            border:2px solid {p['accent']};
            border-radius:28px;
            font-size:22px;
            color:{p['accent']};
        }}
        #title{{ font-size:22px; font-weight:bold; color:{title_col};
                 border:none; }}
        #subtitle{{ font-size:10px; font-weight:600; color:{p['dim']};
                    letter-spacing:2px; border:none; }}
        """)
        for card in (self.cpu, self.ram, self.internet, self.claude,
                     self.cost, self.balance, self.voice, self.memory,
                     self.clock):
            card.retheme()

    def update_status(self):

        cpu = psutil.cpu_percent()

        ram = psutil.virtual_memory().percent

        self.cpu.value.setText(
            f"{cpu:.0f}%"
        )

        self.ram.value.setText(
            f"{ram:.0f}%"
        )

        self.internet.value.setText(
            "Online"
        )

        self.claude.value.setText(
            "Ready"
        )

        self.voice.value.setText(
            "Ready"
        )

        self.memory.value.setText(
            "Active"
        )

        if self.controller is not None:
            try:
                today, month, session = self.controller.cost_summary()
                self.cost.value.setText(f"${today:.2f}")
                self.cost.setToolTip(
                    f"This session: ${session:.4f}\n"
                    f"This month: ${month:.4f}\n"
                    f"(Say 'cost report' for full breakdown)")
            except Exception:
                pass

            # remaining credit — green while healthy, amber under $5,
            # red under $1 so an empty tank never sneaks up on you
            try:
                left = None
                if hasattr(self.controller, "balance_remaining"):
                    left = self.controller.balance_remaining()
                if left is None:
                    self.balance.hide()
                else:
                    self.balance.show()
                    self.balance.value.setText(f"${left:.2f}")
                    col = ("#2ecc71" if left >= 5.0
                           else "#facc15" if left >= 1.0 else "#ff5566")
                    self.balance.value.setStyleSheet(
                        f"border:none;background:transparent;"
                        f"font-size:15px;font-weight:bold;color:{col};")
            except Exception:
                pass

        self.clock.value.setText(

            datetime.now().strftime(

                "%H:%M:%S"

            )

        )
