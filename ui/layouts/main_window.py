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
from PySide6.QtWidgets import QPushButton

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

        self.setWindowTitle("ALLISON OS")

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

        # ── START CLEAN ──────────────────────────────────────────────
        # Hidden by default: the HUD is the orb and the conversation,
        # and the agents/memory/system panel comes out when he asks for
        # it. Ctrl+B or the edge handle brings it back.
        try:
            from PySide6.QtGui import QKeySequence, QShortcut
            self._sc_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
            self._sc_sidebar.activated.connect(self._toggle_sidebar_hidden)
        except Exception as e:
            print(f"[UI] Ctrl+B shortcut unavailable: {e}")
        try:
            self.sidebar.hide_sidebar(animate=False)
            self.sidebar_handle.setText("\u203a")
            self._place_sidebar_handle()
        except Exception as e:
            print(f"[UI] could not start with the sidebar hidden: {e}")

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

        # ── EDGE HANDLE ──────────────────────────────────────────────
        # Lives on the window, NOT inside the sidebar: once the sidebar
        # animates to width 0 nothing inside it can be clicked, so the
        # way back has to be outside it. Sits against the left edge,
        # always visible, and stays out of the way at 18px wide.
        self.sidebar_handle = QPushButton("\u203a", self)
        self.sidebar_handle.setCursor(Qt.PointingHandCursor)
        self.sidebar_handle.setFixedSize(18, 74)
        self.sidebar_handle.setToolTip(
            "Show agents, memory and system (Ctrl+B)")
        self.sidebar_handle.setStyleSheet("""
            QPushButton {
                background: rgba(12,28,43,200);
                color: #3dd8ff;
                border: 1px solid #123048;
                border-left: none;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                font-size: 15px; font-weight: 700;
            }
            QPushButton:hover { background: rgba(20,52,78,235); color:#7fe3ff; }
        """)
        self.sidebar_handle.clicked.connect(self._toggle_sidebar_hidden)
        self.sidebar_handle.raise_()

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
                       activity_provider=lambda: self.controller.brain_activity(),
                       study_provider=lambda: self.controller.study_progress()),
            PlaceholderPage("Research",
                "Say 'study <topic>' — knowledge is saved permanently."),
            PlaceholderPage("Internet",
                "Ask Allison anything — she searches the web with tools."),
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

        # full-screen "JARVIS" focus overlay (hidden until turned on)
        from ui.widgets.focus_view import FocusView
        self._focus_on = False
        self.focus = FocusView(
            central,
            activity_provider=lambda: self.controller.brain_activity(),
            memory_provider=lambda: self.controller.memory_count(),
            on_exit=lambda: self.set_focus_mode(False))
        self.focus.setGeometry(0, 0, central.width(), central.height())
        self.focus.hide()

        # ALWAYS-ON-TOP desktop orb — she floats in the corner of the whole
        # screen, over every app, always there while you work or talk.
        try:
            from ui.widgets.desktop_orb import DesktopOrb
            self.desktop_orb = DesktopOrb(self.controller,
                                          on_click=self._show_from_orb)
            # PRESENCE, NOT CLUTTER. She used to float over everything
            # permanently, including over her own interface. Now the orb
            # is the version of her you get when the interface ISN'T
            # there — minimised, hidden to tray, or another window in
            # front. _sync_desktop_orb() below owns that decision.
            self.desktop_orb.hide()
        except Exception as e:
            print(f"[DesktopOrb] {e}")
            self.desktop_orb = None

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
        if hasattr(self, "focus"):
            try:
                self.focus.retheme()
            except Exception:
                pass

    # ── ORB PRESENCE ────────────────────────────────────────────────
    # One rule: the floating orb is visible exactly when the main
    # interface is not. Close her to tray, minimise her, and she is
    # still there in the corner. Open the interface and she steps back
    # out of the way, because you are already looking at her.

    def _sync_desktop_orb(self):
        orb = getattr(self, "desktop_orb", None)
        if orb is None:
            return
        try:
            interface_up = self.isVisible() and not self.isMinimized()
            if interface_up and orb.isVisible():
                orb.hide()
            elif not interface_up and not orb.isVisible():
                orb.show()
                orb.raise_()
        except Exception as e:
            print(f"[DesktopOrb] sync: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_desktop_orb()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_desktop_orb()

    def changeEvent(self, event):
        # catches minimise/restore, which do NOT fire show/hide
        super().changeEvent(event)
        try:
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.Type.WindowStateChange:
                self._sync_desktop_orb()
        except Exception:
            pass

    def _on_remote_message(self, role, text):
        """A message that came from the phone."""
        try:
            if role == "user":
                self.console.append_user(f"{text}   · from your phone")
            elif role == "allison":
                self.console.append_response(text)
            else:
                self.console.append_system(text)
        except Exception as e:
            print(f"[UI] remote message: {e}")

    def _show_from_orb(self):
        """Click the floating desktop orb → bring the full window forward."""
        try:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._sync_desktop_orb()
        except Exception as e:
            print(f"[DesktopOrb] show: {e}")

    # ── full-screen JARVIS focus mode ────────────────────────────────
    def set_focus_mode(self, on: bool):
        """Full-takeover view: hide the whole dashboard chrome and show
        only the orb (plus whatever task she's doing) — Huw-Prosser
        style. The dashboard is untouched underneath; turning this off
        restores it exactly."""
        self._focus_on = bool(on)
        c = self.centralWidget()
        for w in (getattr(self, "header", None), getattr(self, "sidebar", None),
                  getattr(self, "workspace", None), getattr(self, "console", None),
                  getattr(self, "footer", None)):
            if w is not None:
                w.setVisible(not on)
        if on:
            self.focus.setGeometry(0, 0, c.width(), c.height())
            self.focus.clear_content()
            self.focus.show()
            self.focus.raise_()
        else:
            self.focus.hide()

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

        # ── THE PHONE, SHOWING UP ON THE DESK ────────────────────────
        # Anything said on the phone lands on the shared transcript and
        # arrives here as a signal, so the desk console shows it as it
        # happens. Marked so it is obvious which window it came from —
        # one conversation, but you can still see where he was standing.
        self.controller.remoteMessage.connect(self._on_remote_message)

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
        # full-screen focus mode toggle: "→ focus_mode:on" / ":off"
        fprefix = "→ focus_mode:"
        if raw.startswith(fprefix):
            self.set_focus_mode(raw[len(fprefix):].strip() == "on")
            return
        # a request to auto-close a panel (e.g. the study bar when done)
        cprefix = "→ close_info:"
        if raw.startswith(cprefix):
            pid = raw[len(cprefix):].strip()
            from PySide6.QtCore import QTimer
            if self._focus_on:
                QTimer.singleShot(2500, self.focus.clear_content)
            else:
                QTimer.singleShot(2500, lambda: self._close_info_panel(pid))
            return
        prefix = "→ show_info:"
        if not raw.startswith(prefix):
            return
        import json as _json
        try:
            payload = _json.loads(raw[len(prefix):])
        except Exception:
            return
        # in focus mode the task takes the whole screen instead of a panel
        if self._focus_on:
            self.focus.show_content(
                payload.get("title", "ALLISON"),
                payload.get("content", ""),
                payload.get("kind", "text"))
            return
        self.show_info_panel(
            payload.get("id", "info"),
            payload.get("title", "ALLISON"),
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

        # ── RETIRE WHEN STALE ────────────────────────────────────────
        # Panels used to arrive and stay forever, so a long session
        # silted up with a dozen dead windows over the HUD. Each one now
        # dismisses itself once it has gone quiet, unless Shaun has
        # dragged it (moving it is how you say "I want this one"), or
        # it is an image he probably wants to keep looking at.
        try:
            self._arm_panel_retire(panel_id, panel, kind)
        except Exception as e:
            print(f"[UI] could not arm panel retire: {e}")

    PANEL_TTL_MS = 90_000          # a minute and a half of no updates

    def _arm_panel_retire(self, panel_id, panel, kind="text"):
        from PySide6.QtCore import QTimer
        timers = getattr(self, "_panel_timers", None)
        if timers is None:
            timers = self._panel_timers = {}
        old_t = timers.get(panel_id)
        if old_t is not None:
            old_t.stop()                       # each update resets the clock
        if kind == "image":
            return                             # leave pictures up
        t = QTimer(self)
        t.setSingleShot(True)

        def _retire():
            try:
                if panel.user_moved or not panel.isVisible():
                    return                     # he claimed it, or it is gone
                self._fade_out_panel(panel)
            except Exception:
                pass

        t.timeout.connect(_retire)
        t.start(self.PANEL_TTL_MS)
        timers[panel_id] = t

    def _fade_out_panel(self, panel):
        """Fade rather than vanish, so it reads as tidying up rather
        than something crashing."""
        try:
            from PySide6.QtCore import QPropertyAnimation
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            eff = QGraphicsOpacityEffect(panel)
            panel.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", panel)
            anim.setDuration(420)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)

            def _done():
                panel.hide()
                panel.setGraphicsEffect(None)
                try:
                    self._update_brain_compact()
                except Exception:
                    pass
            anim.finished.connect(_done)
            anim.start()
            panel._fade_anim = anim            # keep a ref
        except Exception:
            panel.hide()

    def _close_info_panel(self, panel_id: str):
        """Hide a mini-tab (used to auto-dismiss the study bar when the
        study finishes, so it doesn't linger over the chat)."""
        panel = self.info_panels.get(panel_id)
        if panel is not None:
            try:
                panel.hide()
            except Exception:
                pass
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
        # keep panels clear of the conversation console on the right, so
        # they never cover the chat. Reserve the console's width + margin.
        reserve = 40
        try:
            if hasattr(self, "console") and self.console.isVisible():
                reserve = self.console.width() + 40
        except Exception:
            reserve = 440
        base_x = c.width() - panel.width() - reserve
        base_y = 150
        offset = (idx % 5) * 32
        # never slide under the sidebar either
        panel.move(max(250, base_x - offset), base_y + offset)

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

    # ── sidebar hide / reveal ────────────────────────────────────────

    def _toggle_sidebar_hidden(self):
        """Slide the sidebar away or back, and flip the handle arrow."""
        try:
            shown = self.sidebar.toggle_hidden()
        except Exception as e:
            print(f"[UI] sidebar toggle failed: {e}")
            return
        self.sidebar_handle.setText("\u2039" if shown else "\u203a")
        self.sidebar_handle.setToolTip(
            "Hide the panel (Ctrl+B)" if shown
            else "Show agents, memory and system (Ctrl+B)")
        self._place_sidebar_handle()

    def _place_sidebar_handle(self):
        """Pin the handle to the sidebar's right edge, or the window's
        left edge when the sidebar is hidden."""
        try:
            c = self.centralWidget()
            w = self.sidebar.width() if not getattr(
                self.sidebar, "hidden", False) else 0
            self.sidebar_handle.move(max(0, w),
                                     max(0, (c.height() // 2) - 37))
            self.sidebar_handle.raise_()
        except Exception:
            pass

    def resizeEvent(self, event):

        c = self.centralWidget()
        if hasattr(self, "sidebar_handle"):
            self._place_sidebar_handle()
        if hasattr(self, "backdrop"):
            self.backdrop.setGeometry(0, 0, c.width(), c.height())
        if hasattr(self, "focus") and self.focus.isVisible():
            self.focus.setGeometry(0, 0, c.width(), c.height())
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
        self.tray.setToolTip("Allison — running. Say 'Allison'.")

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
            self._sync_desktop_orb()      # she reappears in the corner
            self.tray.showMessage(
                "JARVIS",
                "Still here, sir — running in the background. "
                "Say 'Allison' or click the orb to bring me back.",
                QSystemTrayIcon.Information, 4000)
            return

        try:
            self.controller.shutdown()
        except Exception:
            pass

        event.accept()