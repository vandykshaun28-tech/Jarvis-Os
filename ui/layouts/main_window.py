import os

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
    QApplication,
)
from PySide6.QtGui import QIcon, QAction

from ui.components.header import Header
from ui.components.sidebar import Sidebar
from ui.components.console import Console
from ui.components.footer import Footer

from ui.pages.dashboard import DashboardPage
from ui.pages.agents import AgentsPage
from ui.pages.trading import TradingPage
from ui.pages.shopify import ShopifyPage
from ui.pages.placeholder import PlaceholderPage
from ui.widgets.grid_backdrop import GridBackdrop
from ui.widgets.camera_panel import CameraPanel

from core.controller import JarvisController


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("JARVIS OS v20")

        self.resize(1700, 950)

        self.setStyleSheet("background:#04080f;")

        # ----------------------------------------
        # Create Controller
        # ----------------------------------------

        self.controller = JarvisController()

        self._really_quit = False

        self.build_ui()

        self.connect_signals()

        self.build_tray()

    # --------------------------------------------------

    def build_ui(self):

        central = QWidget()

        central.setStyleSheet("background:transparent;")

        self.setCentralWidget(central)

        # holographic grid painted behind EVERYTHING
        self.backdrop = GridBackdrop(central)
        self.backdrop.lower()

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

        # Live data providers, resolved lazily once the brain is up
        agents_provider  = lambda: self.controller.agent_snapshots()
        trading_provider = lambda: self.controller.get_agent("trading")
        shopify_provider = lambda: self.controller.get_agent("shopify")
        mind_provider    = lambda: self.controller.get_agent("mind")
        listen_provider  = lambda: self.controller.listener

        self.dashboard = DashboardPage(providers={
            "trading":  trading_provider,
            "mind":     mind_provider,
            "listener": listen_provider,
        })

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

        # floating live camera mini tab (hidden until needed)
        self.camera_panel = CameraPanel(central)

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

        self.console.filesSubmitted.connect(
            self.controller.ask_with_files
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

        # Controller -> dashboard stage (orb + NOW card)

        self.controller.processingStarted.connect(
            self.dashboard.set_thinking
        )

        self.controller.processingFinished.connect(
            self.dashboard.set_idle
        )

        # Camera mini tab: explicit commands + auto-open when he looks

        self.controller.cameraPanel.connect(self._toggle_camera_panel)

        self.controller.progressReceived.connect(self._watch_for_camera_use)

        # Voice/mic startup diagnostics
        for note in getattr(self.controller, "startup_notes", []):
            self.console.append_system(note)

        print("[MainWindow] Signals connected.")

    # --------------------------------------------------

    def _toggle_camera_panel(self, show):

        if show:
            self.camera_panel.open_panel()
            self._place_camera_panel()
        else:
            self.camera_panel.close_panel()

    def _watch_for_camera_use(self, text):

        if str(text).strip() == "→ camera_look":
            self._toggle_camera_panel(True)

    def _place_camera_panel(self):

        if self.camera_panel.user_moved:
            self.camera_panel.raise_()
            return
        c = self.centralWidget()
        self.camera_panel.move(
            c.width() - self.camera_panel.width() - 460,
            c.height() - self.camera_panel.height() - 80,
        )
        self.camera_panel.raise_()

    def resizeEvent(self, event):

        c = self.centralWidget()
        if hasattr(self, "backdrop"):
            self.backdrop.setGeometry(0, 0, c.width(), c.height())
        if hasattr(self, "camera_panel") and self.camera_panel.isVisible():
            self._place_camera_panel()
        super().resizeEvent(event)

    # --------------------------------------------------

    # --------------------------------------------------
    # System tray — closing the window hides JARVIS to the
    # tray; he keeps running and listening in the background.
    # --------------------------------------------------

    def build_tray(self):

        self.tray = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "assets", "jarvis_orb.ico")

        self.tray = QSystemTrayIcon(QIcon(icon_path), self)
        self.tray.setToolTip("JARVIS — running. Say 'hey jarvis'.")

        menu = QMenu()
        act_open = QAction("Open JARVIS", menu)
        act_open.triggered.connect(self._restore_from_tray)
        act_exit = QAction("Shut down JARVIS", menu)
        act_exit.triggered.connect(self._really_exit)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._restore_from_tray()
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick)
            else None)
        self.tray.show()

    def _restore_from_tray(self):

        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _really_exit(self):

        self._really_quit = True
        try:
            self.controller.shutdown()
        except Exception:
            pass
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):

        # X button = minimize to tray, NOT exit. JARVIS stays alive,
        # agents keep working, ears stay open. Real exit lives in the
        # tray menu ("Shut down JARVIS").
        if self.tray is not None and not self._really_quit:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "JARVIS",
                "Still here, sir — running in the background. "
                "Say 'hey jarvis' or click the orb to bring me back.",
                QSystemTrayIcon.Information, 4000)
            return

        try:
            self.controller.shutdown()
        except Exception:
            pass

        event.accept()