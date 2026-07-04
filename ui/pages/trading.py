"""
Trading page — live prices, paper portfolio and recent trades.
Reads snapshots from the Trading agent via a provider callable.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import QTimer


def _panel(title):
    box = QFrame()
    box.setStyleSheet(
        "QFrame{background:#0a1420;border:1px solid #12324a;border-radius:12px;}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 12, 16, 12)
    lay.setSpacing(6)
    t = QLabel(title)
    t.setStyleSheet("color:#22d3ee;font-size:11px;font-weight:700;"
                    "letter-spacing:2px;border:none;")
    lay.addWidget(t)
    return box, lay


class TradingPage(QWidget):
    """provider: () -> trading agent instance or None"""

    def __init__(self, provider=None):
        super().__init__()
        self.provider = provider or (lambda: None)
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(10)

        header = QLabel("TRADING — PAPER MODE (real prices, pretend money)")
        header.setStyleSheet("color:#f5a623;font-size:12px;font-weight:700;"
                             "letter-spacing:2px;border:none;")
        root.addWidget(header)

        prices_box, plake = _panel("LIVE PRICES (LUNO)")
        self.prices_lbl = QLabel("Waiting for first tick...")
        self.prices_lbl.setStyleSheet(
            "color:#e8f6ff;font-size:16px;font-weight:600;border:none;")
        plake.addWidget(self.prices_lbl)
        root.addWidget(prices_box)

        port_box, polay = _panel("PAPER PORTFOLIO")
        self.port_lbl = QLabel("—")
        self.port_lbl.setStyleSheet(
            "color:#c7e3f5;font-size:12px;border:none;font-family:Consolas;")
        self.port_lbl.setWordWrap(True)
        polay.addWidget(self.port_lbl)
        root.addWidget(port_box)

        trades_box, tlay = _panel("RECENT TRADES & SIGNALS")
        self.trades_lbl = QLabel("No trades yet. The SMA strategy will act "
                                 "once it has ~30 minutes of price history, "
                                 "or tell JARVIS e.g. 'buy R5000 of bitcoin on paper'.")
        self.trades_lbl.setStyleSheet(
            "color:#c7e3f5;font-size:11px;border:none;font-family:Consolas;")
        self.trades_lbl.setWordWrap(True)
        tlay.addWidget(self.trades_lbl)
        root.addWidget(trades_box)
        root.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def refresh(self):
        try:
            agent = self.provider()
        except Exception:
            agent = None
        if agent is None:
            return
        try:
            if agent.latest:
                self.prices_lbl.setText(
                    "      ".join(f"{p}   R{v:,.0f}" for p, v in agent.latest.items()))
            self.port_lbl.setText(agent.portfolio_report())
            trades = agent.portfolio.get("trades", [])[:8]
            if trades:
                self.trades_lbl.setText("\n".join(
                    f"{t['time']}  {t['detail'][:90]}  [{t['reason']}]" for t in trades))
        except Exception:
            pass
