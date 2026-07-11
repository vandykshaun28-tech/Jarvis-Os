"""
Shopify page — connection state and the agent's recent activity.
Entering this tab also opens your Shopify admin in the browser.
"""

import time
import webbrowser

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import QTimer

import config


def _admin_url() -> str:
    """Your store's admin if configured, else the general admin page."""
    store = (getattr(config, "SHOPIFY_STORE", "") or "").strip()
    if store:
        handle = store.split(".")[0]
        return f"https://admin.shopify.com/store/{handle}"
    return "https://admin.shopify.com"


class ShopifyPage(QWidget):
    """provider: () -> shopify agent instance or None"""

    def __init__(self, provider=None):
        super().__init__()
        self.provider = provider or (lambda: None)
        self._last_open = 0.0
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        title = QLabel("SHOPIFY STORE AGENT")
        title.setStyleSheet("color:#22d3ee;font-size:13px;font-weight:700;"
                            "letter-spacing:3px;border:none;")
        root.addWidget(title)

        box = QFrame()
        box.setStyleSheet("QFrame{background:#0a1420;border:1px solid #12324a;"
                          "border-radius:12px;}")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 12)

        self.status_lbl = QLabel("—")
        self.status_lbl.setStyleSheet(
            "color:#e8f6ff;font-size:13px;font-weight:600;border:none;")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        self.events_lbl = QLabel("")
        self.events_lbl.setStyleSheet(
            "color:#c7e3f5;font-size:11px;border:none;font-family:Consolas;")
        self.events_lbl.setWordWrap(True)
        lay.addWidget(self.events_lbl)
        root.addWidget(box)

        help_box = QFrame()
        help_box.setStyleSheet("QFrame{background:#0a1420;border:1px solid #12324a;"
                               "border-radius:12px;}")
        hlay = QVBoxLayout(help_box)
        hlay.setContentsMargins(16, 12, 16, 12)
        self.help_lbl = QLabel(
            "To connect your store:\n"
            "1. Shopify admin → Settings → Apps and sales channels → Develop apps\n"
            "2. Create an app with read_orders and read_products scopes\n"
            "3. Set environment variables SHOPIFY_STORE and SHOPIFY_TOKEN\n"
            "   (or paste them into config.py) and restart JARVIS.\n\n"
            "Once connected, JARVIS announces new orders as they land, flags\n"
            "low stock every morning, and gives a spoken sales summary at "
            f"{config.SHOPIFY_SUMMARY_HOUR}:00.")
        self.help_lbl.setStyleSheet("color:#7ba7c2;font-size:11px;border:none;")
        hlay.addWidget(self.help_lbl)
        root.addWidget(help_box)
        root.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def showEvent(self, event):
        """Fires when you switch INTO this tab — open the real store.
        Debounced so window restores don't spam browser tabs."""
        super().showEvent(event)
        now = time.time()
        if now - self._last_open > 15:
            self._last_open = now
            try:
                webbrowser.open(_admin_url())
            except Exception as e:
                print(f"[Shopify] couldn't open browser: {e}")

    def refresh(self):
        try:
            agent = self.provider()
        except Exception:
            agent = None
        if agent is None:
            self.status_lbl.setText("Agent starting up...")
            return
        snap = agent.snapshot()
        state = snap["status"].replace("_", " ").upper()
        self.status_lbl.setText(f"● {state} — {snap['last_message'] or 'no activity yet'}")
        self.help_lbl.setVisible(not agent.configured)
        self.events_lbl.setText(
            "\n".join(f"{t}  {m}" for t, m in snap["events"][:10]))
