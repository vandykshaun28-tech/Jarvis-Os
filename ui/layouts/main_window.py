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

# Pages
from ui.pages.dashboard import DashboardPage


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("JARVIS OS v20")

        self.resize(1700, 950)

        self.build_ui()

    def build_ui(self):

        central = QWidget()

        self.setCentralWidget(central)

        root = QVBoxLayout()

        root.setContentsMargins(8, 8, 8, 8)

        root.setSpacing(8)

        central.setLayout(root)

        # ===================================
        # Header
        # ===================================

        self.header = Header()

        root.addWidget(self.header)

        # ===================================
        # Main Body
        # ===================================

        body = QHBoxLayout()

        body.setSpacing(8)

        root.addLayout(body, 1)

        # Sidebar

        self.sidebar = Sidebar()

        body.addWidget(self.sidebar)

        # ===================================
        # Workspace
        # ===================================

        self.workspace = QStackedWidget()

        body.addWidget(self.workspace, 1)

        # Dashboard Page

        self.dashboard = DashboardPage()

        self.workspace.addWidget(self.dashboard)

        # Show Dashboard first

        self.workspace.setCurrentWidget(self.dashboard)

        # ===================================
        # Console
        # ===================================

        self.console = Console()

        body.addWidget(self.console)

        # ===================================
        # Footer
        # ===================================

        self.footer = Footer()

        root.addWidget(self.footer)