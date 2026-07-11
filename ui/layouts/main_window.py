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
from PySide6.QtCore import Qt

from ui.components.header import Header
from ui.components.sidebar import Sidebar
from ui.components.console import Console
from ui.components.footer import Footer

from ui.pages.dashboard import DashboardPage
from ui.pages.agents import AgentsPage
from ui.pages.trading import TradingPage
from ui.pages.shopify import ShopifyPage
from ui.pages.placeholder import PlaceholderPage
from ui.pages.settings import SettingsPage
from core import settings as user_settings
from ui.widgets.grid_backdrop import GridBackdrop
from ui.widgets.camera_panel import CameraPanel
from ui.widgets.info_panel import InfoPanel

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

        self.header = Header(controller=self.controller)

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
            "activity": lambda: self.controller.brain_activity(),
            "memories": lambda: self.controller.memory_count(),
        })

        # Order matches the sidebar buttons exactly
        self.pages = [
            self.dashboard,                                       # Dashboard
            AgentsPage(provider=agents_provider,
                       activity_provider=lambda: self.controller.brain_activity()),
            PlaceholderPage("Research",
                "Say 'study <topic>' — knowledge is saved permanently."),
            PlaceholderPage("Internet",
                "Ask JARVIS anything — he searches the web with tools."),
            TradingPage(provider=trading_provider),               # Trading
            PlaceholderPage("PLC"),                               # PLC
            PlaceholderPage("Vehicle"),                           # Vehicle
            ShopifyPage(provider=shopify_provider),               # Shopify
            SettingsPage(window_ref=self),                        # Settings
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
        self.info_panels = {}   # panel_id -> InfoPanel, so repeat asks reuse it

        # apply the saved theme + accent immediately
        from ui.styles.theme_manager import ACCENTS, set_accent
        set_accent(ACCENTS.get(user_settings.get("accent"), None))
        self.apply_theme(user_settings.get("theme"))

    def apply_theme(self, name: str):
        """Switch the whole interface between dark and light. Sets the
        active palette then asks every themed surface to restyle."""
        from ui.styles.theme_manager import set_theme
        set_theme(name)
        if hasattr(self, "backdrop"):
            self.backdrop.update()
        for widget in (getattr(self, "sidebar", None),
                       getattr(self, "header", None),
                       getattr(self, "console", None),
                       getattr(self, "footer", None)):
            if widget is not None and hasattr(widget, "retheme"):
                try:
                    widget.retheme()
                except Exception as e:
                    print(f"[Theme] {type(widget).__name__}: {e}")

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

        # Live mic state → the listening pill only appears while
        # JARVIS is actually capturing a command
        if hasattr(self.controller, "listeningChanged") and \
                hasattr(self.dashboard, "set_listening"):
            self.controller.listeningChanged.connect(
                self.dashboard.set_listening
            )

        # Voice mute button ↔ controller (voice phrases sync the icon too)

        self.console.muteClicked.connect(
            self.controller.toggle_voice_mute
        )

        self.console.stopClicked.connect(
            self.controller.stop_speaking
        )

        self.controller.voiceMuteChanged.connect(
            self.console.set_mute_state
        )

        # Camera mini tab: explicit commands + auto-open when he looks

        self.controller.cameraPanel.connect(self._toggle_camera_panel)

        self.controller.progressReceived.connect(self._watch_for_camera_use)

        self.controller.progressReceived.connect(self._watch_for_info_panel)

        # Mini mode — JARVIS shrinks to a corner chat while he works
        self.controller.progressReceived.connect(self._watch_for_mini_mode)
        if hasattr(self.controller, "miniModeChanged"):
            self.controller.miniModeChanged.connect(self.set_mini_mode)
        if hasattr(self.console, "restoreClicked"):
            self.console.restoreClicked.connect(
                lambda: self.set_mini_mode(False))

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
            # wait a beat so the BRAIN gets the webcam first for its
            # snapshot — the live panel takes over a moment later
            # (only one process may hold a webcam at a time)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2500, lambda: self._toggle_camera_panel(True))

    def _watch_for_mini_mode(self, text):
        t = str(text).strip()
        if t == "→ mini_mode:on":
            self.set_mini_mode(True)
        elif t == "→ mini_mode:off":
            self.set_mini_mode(False)

    def set_mini_mode(self, on: bool):
        """Shrink JARVIS to a floating, always-on-top chat box in the
        BOTTOM-LEFT corner (so Shaun can watch him drive an app or the
        browser and still talk to him), or restore the full interface."""
        on = bool(on)
        if on == getattr(self, "_mini_mode", False):
            return
        self._mini_mode = on
        try:
            if on:
                self._mini_saved_geo = self.saveGeometry()
                self._mini_was_max = self.isMaximized()
                for w in (self.sidebar, self.header, self.footer,
                          self.workspace):
                    w.hide()
                if self.console.collapsed:
                    self.console.toggle_collapsed()
                if hasattr(self.console, "mini_btn"):
                    self.console.mini_btn.show()
                self.showNormal()
                self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                self.show()
                from PySide6.QtGui import QGuiApplication
                scr = QGuiApplication.primaryScreen().availableGeometry()
                w, h = 442, min(640, scr.height() - 60)
                self.resize(w, h)
                self.move(scr.left() + 10, scr.bottom() - h - 10)
            else:
                self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                if hasattr(self.console, "mini_btn"):
                    self.console.mini_btn.hide()
                for w in (self.sidebar, self.header, self.footer,
                          self.workspace):
                    w.show()
                self.show()
                if getattr(self, "_mini_saved_geo", None):
                    self.restoreGeometry(self._mini_saved_geo)
                if getattr(self, "_mini_was_max", False):
                    self.showMaximized()
        except Exception as e:
            print(f"[MiniMode] {e}")

    def _watch_for_info_panel(self, text):
        """JARVIS's mini-tab trigger — brain.py sends a marker like
        '→ show_info:{json payload}' through the same progress channel
        used for tool-activity markers. Parse it and pop/update a panel."""
        raw = str(text)
        prefix = "→ show_info:"
        if not raw.startswith(prefix):
            return
        import json as _json
        try:
            payload = _json.loads(raw[len(prefix):])
        except Exception:
            return
        self.show_info_panel(
            payload.get("id", "info"),
            payload.get("title", "JARVIS"),
            payload.get("content", ""),
            payload.get("kind", "text"),
        )

    def show_info_panel(self, panel_id: str, title: str, content: str,
                        kind: str = "text"):
        """Create or reuse a mini-tab. Repeat calls with the same
        panel_id update the existing panel in place instead of
        spawning a new one, so 'weather' panel just refreshes."""
        panel = self.info_panels.get(panel_id)
        if panel is None:
            panel = InfoPanel(panel_id, self.centralWidget())
            panel.on_close = self._update_brain_compact
            self.info_panels[panel_id] = panel
            self._place_info_panel(panel, is_new=True)
        panel.set_content(title, content, kind)
        panel.show()
        panel.raise_()
        if not panel.user_moved:
            self._place_info_panel(panel, is_new=False)
        self._update_brain_compact()

    def _update_brain_compact(self):
        """Shrink the brain to the corner while any panel is open."""
        try:
            any_open = any(pnl.isVisible()
                           for pnl in self.info_panels.values())
            if hasattr(self, "camera_panel") and self.camera_panel.isVisible():
                any_open = True
            core = getattr(self.dashboard, "core", None)
            if core and hasattr(core, "set_compact"):
                core.set_compact(any_open)
        except Exception as e:
            print(f"[Brain compact] {e}")

    def _place_info_panel(self, panel, is_new: bool):
        c = self.centralWidget()
        if not c:
            return
        # cascade new panels so several can be open without exactly
        # overlapping; index by creation order among open panels
        idx = list(self.info_panels.values()).index(panel)
        base_x = c.width() - panel.width() - 60
        base_y = 140
        offset = (idx % 5) * 32
        panel.move(max(0, base_x - offset), base_y + offset)

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
        if hasattr(self, "info_panels"):
            for panel in self.info_panels.values():
                if panel.isVisible():
                    panel._clamp_to_parent()
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