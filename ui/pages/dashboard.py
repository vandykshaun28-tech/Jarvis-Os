from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QGridLayout,
    QFrame,
)

from ui.widgets.ai_core.ai_core import AICore


class DashboardPage(QWidget):

    def __init__(self):

        super().__init__()

        self.build_ui()

    def build_ui(self):

        root = QVBoxLayout()

        root.setContentsMargins(20, 20, 20, 20)

        root.setSpacing(20)

        self.setLayout(root)

        # =====================================================
        # AI CORE
        # =====================================================

        ai = QFrame()

        ai.setObjectName("ai_core")

        ai.setMinimumHeight(600)

        ai_layout = QVBoxLayout()

        ai_layout.setContentsMargins(20, 20, 20, 20)

        ai_layout.setSpacing(0)

        ai.setLayout(ai_layout)

        self.ai_core = AICore()

        ai_layout.addWidget(self.ai_core)

        root.addWidget(ai)

        # =====================================================
        # DASHBOARD GRID
        # =====================================================

        grid = QGridLayout()

        grid.setSpacing(15)

        root.addLayout(grid)

        cards = [

            "System Status",

            "Active Agents",

            "Recent Activity",

            "Quick Actions",

        ]

        for i, name in enumerate(cards):

            card = QFrame()

            card.setObjectName("dashboard_card")

            card.setMinimumHeight(170)

            layout = QVBoxLayout()

            layout.setContentsMargins(15, 15, 15, 15)

            layout.setSpacing(10)

            card.setLayout(layout)

            title = QLabel(name)

            title.setObjectName("card_title")

            layout.addWidget(title)

            layout.addStretch()

            row = i // 2

            col = i % 2

            grid.addWidget(card, row, col)

        # =====================================================
        # STYLE
        # =====================================================

        self.setStyleSheet("""

        QWidget{

            background:transparent;

        }

        #ai_core{

            background:#071019;

            border:1px solid #123b5d;

            border-radius:12px;

        }

        #dashboard_card{

            background:#071019;

            border:1px solid #123b5d;

            border-radius:10px;

        }

        #card_title{

            color:white;

            font-size:14px;

            font-weight:bold;

            border:none;

        }

        """)