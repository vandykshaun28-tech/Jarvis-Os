from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
)

from ui.components.header import Header
from ui.components.sidebar import Sidebar
from ui.components.console import Console
from ui.components.footer import Footer

from ui.pages.dashboard import DashboardPage
from ui.pages.agents import AgentsPage
from ui.pages.trading import TradingPage
from ui.pages.shopify import ShopifyPage
from ui.pages.placeholder import PlaceholderPage

from core.controller import JarvisController


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("JARVIS OS v20")

        self.resize(1700, 950)

        self.setStyleSheet("background:#05070d;")

        # ----------------------------------------
        # Create Controller
        # ----------------------------------------

        self.controller = JarvisController()

        self.build_ui()

        self.connect_signals()

    # --------------------------------------------------

    def build_ui(self):

        central = QWidget()

        central.setStyleSheet("background:#05070d;")

        self.setCentralWidget(central)

        root = QVBoxLayout()

        root.setContentsMargins(14, 14, 14, 14)

        root.setSpacing(14)

        central.setLayout(root)

        # ----------------------------------------
        # Header
        # ----------------------------------------

        self.header = Header()

        root.addWidget(self.header)

        # ----------------------------------------
        # Body
        # ----------------------------------------

        body = QHBoxLayout()

        body.setSpacing(14)

        root.addLayout(body, 1)

        # ----------------------------------------
        # Sidebar
        # ----------------------------------------

        self.sidebar = Sidebar()

        body.addWidget(self.sidebar)

        # ----------------------------------------
        # Workspace
        # ----------------------------------------

        self.workspace = QStackedWidget()

        body.addWidget(self.workspace, 1)

        self.dashboard = DashboardPage()

        # Live data providers, resolved lazily once the brain is up
        agents_provider  = lambda: self.controller.agent_snapshots()
        trading_provider = lambda: self.controller.get_agent("trading")
        shopify_provider = lambda: self.controller.get_agent("shopify")

        # Order matches the sidebar buttons exactly
        self.pages = [
            self.dashboard,                                       # Dashboard
            AgentsPage(provider=agents_provider),                 # AI Agents
            PlaceholderPage("Research",
                "Say 'study <topic>' — knowledge is saved permanently."),
            PlaceholderPage("Internet",
                "Ask JARVIS anything — he searches the web with tools."),
            TradingPage(provider=trading_provider),               # Trading
            PlaceholderPage("PLC"),                               # PLC
            PlaceholderPage("Vehicle"),                           # Vehicle
            ShopifyPage(provider=shopify_provider),               # Shopify
            PlaceholderPage("Settings",
                "Paths and agent settings live in config.py for now."),
        ]

        for page in self.pages:
            self.workspace.addWidget(page)

        self.workspace.setCurrentWidget(self.dashboard)

        # ----------------------------------------
        # Console
        # ----------------------------------------

        self.console = Console()

        body.addWidget(self.console)

        # ----------------------------------------
        # Footer
        # ----------------------------------------

        self.footer = Footer()

        root.addWidget(self.footer)

    # --------------------------------------------------

    def connect_signals(self):

        print("[MainWindow] Connecting signals...")

        # Sidebar navigation -> workspace pages

        for i, button in enumerate(self.sidebar.buttons):

            if i < len(self.pages):

                button.clicked.connect(
                    lambda _=False, idx=i: self.workspace.setCurrentIndex(idx)
                )

        # Console -> Controller

        self.console.commandSubmitted.connect(
            self.controller.ask
        )

        # Controller -> Console

        self.controller.responseReceived.connect(
            self.console.append_response
        )

        self.controller.statusChanged.connect(
            self.console.set_status
        )

        self.controller.errorOccurred.connect(
            self.console.append_system
        )

        # Live brain updates (research progress, reminders, agent briefings)

        self.controller.progressReceived.connect(
            self.console.append_system
        )

        # Voice commands show up in the console like typed ones

        self.controller.voiceHeard.connect(
            self.console.append_user
        )

        # Controller -> AI Core

        if hasattr(self.dashboard, "core"):

            if hasattr(self.dashboard.core, "set_thinking"):

                self.controller.processingStarted.connect(
                    self.dashboard.core.set_thinking
                )

            if hasattr(self.dashboard.core, "set_idle"):

                self.controller.processingFinished.connect(
                    self.dashboard.core.set_idle
                )

        print("[MainWindow] Signals connected.")

    # --------------------------------------------------

    def closeEvent(self, event):

        try:

            self.controller.shutdown()

        except Exception:

            pass

        event.accept()