"""
Dashboard — the orb centre-stage, with the concept interface's
floating stage cards (NOW / PAPER P&L / LAST THOUGHT) and the
"listening" pill with an animated equalizer at the bottom.
"""

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QTimer

from ui.widgets.concept_orb import ConceptOrb

CYAN, DIM, ICE, LINE = "#22d3ee", "#5a8bb0", "#e8f6ff", "#12324a"
GREEN, RED = "#2ecc71", "#ff5566"


class StageCard(QFrame):

    def __init__(self, title):
        super().__init__()
        self.setStyleSheet(
            f"QFrame{{background:rgba(8,17,28,0.86);border:1px solid {LINE};"
            f"border-radius:12px;}}")
        self.setFixedWidth(230)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)
        t = QLabel(title)
        t.setStyleSheet(f"color:{DIM};font-size:9px;font-weight:700;"
                        f"letter-spacing:2px;border:none;background:transparent;")
        lay.addWidget(t)
        self.value = QLabel("—")
        self.value.setWordWrap(True)
        self.value.setStyleSheet(f"color:{CYAN};font-size:13px;font-weight:600;"
                                 f"border:none;background:transparent;")
        lay.addWidget(self.value)
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{DIM};font-size:10px;border:none;"
                               f"background:transparent;")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

    def set(self, value, sub="", color=CYAN):
        self.value.setText(str(value))
        self.value.setStyleSheet(f"color:{color};font-size:13px;font-weight:600;"
                                 f"border:none;background:transparent;")
        self.sub.setText(sub)


class ListenPill(QFrame):
    """'listening — say hey jarvis' with a little animated equalizer."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            f"QFrame{{background:rgba(8,17,28,0.85);border:1px solid {LINE};"
            f"border-radius:20px;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 9, 20, 9)
        lay.setSpacing(12)
        self.bars = QLabel("▁▃▅▃▁")
        self.bars.setStyleSheet(f"color:{CYAN};font-size:13px;border:none;"
                                f"background:transparent;")
        lay.addWidget(self.bars)
        self.text = QLabel('listening — say  "hey jarvis"')
        self.text.setStyleSheet(f"color:{DIM};font-size:12px;border:none;"
                                f"background:transparent;")
        lay.addWidget(self.text)
        self._t = 0
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(160)

    def _tick(self):
        self._t += 1
        glyphs = "▁▂▃▄▅▆"
        s = "".join(glyphs[int((math.sin(self._t * 0.9 + i) + 1) * 2.6)]
                    for i in range(5))
        self.bars.setText(s)

    def set_state(self, state, detail=""):
        if state == "offline":
            self.bars.setStyleSheet(f"color:{RED};font-size:13px;border:none;"
                                    f"background:transparent;")
            self.text.setText(detail or "microphone offline — type 'voice status'")
        elif state == "speaking":
            self.text.setText("JARVIS is speaking…")
        else:
            self.bars.setStyleSheet(f"color:{CYAN};font-size:13px;border:none;"
                                    f"background:transparent;")
            self.text.setText('listening — say  "hey jarvis"')


class DashboardPage(QWidget):
    """providers: dict of callables injected by MainWindow
       (trading agent, mind agent, listener state)."""

    def __init__(self, providers=None):
        super().__init__()
        self.providers = providers or {}
        self.build_ui()

    def build_ui(self):
        self.setStyleSheet("QWidget{background:transparent;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.core = ConceptOrb()
        root.addWidget(self.core, 1)

        # floating stage cards, top-left over the orb
        overlay = QWidget(self.core)
        overlay.setStyleSheet("background:transparent;")
        ov = QVBoxLayout(overlay)
        ov.setContentsMargins(18, 18, 0, 0)
        ov.setSpacing(10)
        self.card_now    = StageCard("NOW")
        self.card_pnl    = StageCard("PAPER P&L")
        self.card_thought = StageCard("LAST THOUGHT")
        for c in (self.card_now, self.card_pnl, self.card_thought):
            ov.addWidget(c)
        ov.addStretch()
        overlay.move(0, 0)
        overlay.resize(260, 420)

        # listening pill, bottom-centre
        self.pill = ListenPill()
        pill_row = QHBoxLayout()
        pill_row.addStretch()
        pill_row.addWidget(self.pill)
        pill_row.addStretch()
        root.addLayout(pill_row)
        root.addSpacing(14)

        self.card_now.set("Standing by", "waiting for you, sir")
        self.card_pnl.set("R0.00", "no trades yet")
        self.card_thought.set("…", "the Mind wakes every 30 min")

        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(3000)

    # ── live data ───────────────────────────────
    def refresh(self):
        try:
            self._refresh_trading()
            self._refresh_mind()
            self._refresh_listen()
        except Exception:
            pass

    def _refresh_trading(self):
        get = self.providers.get("trading")
        agent = get() if get else None
        if not agent:
            return
        pf = agent.portfolio
        total = pf.get("cash", 0.0)
        for pair, h in pf.get("holdings", {}).items():
            total += h["units"] * agent.latest.get(pair, h["avg_price"])
        try:
            import config
            start = config.PAPER_STARTING_CASH
        except Exception:
            start = 100_000.0
        pnl = total - start
        col = GREEN if pnl >= 0 else RED
        sign = "+" if pnl >= 0 else "−"
        trades = len(pf.get("trades", []))
        self.card_pnl.set(f"{sign}R{abs(pnl):,.2f}",
                          f"{trades} trades · {agent.price_report()[:40]}", col)

    def _refresh_mind(self):
        get = self.providers.get("mind")
        agent = get() if get else None
        if not agent:
            return
        thought = getattr(agent, "_last_thought", "") or "…"
        self.card_thought.set(f'"{thought[:90]}"', "Mind · autonomous", ICE)

    def _refresh_listen(self):
        get = self.providers.get("listener")
        listener = get() if get else None
        if listener is None:
            self.pill.set_state("offline")
        else:
            self.pill.set_state("listening")

    # ── busy state from controller ──────────────
    def set_thinking(self):
        self.card_now.set("Thinking…", "planning with tools", "#f5a623")
        if hasattr(self.core, "set_thinking"):
            try: self.core.set_thinking()
            except Exception: pass

    def set_idle(self):
        self.card_now.set("Standing by", "waiting for you, sir")
        if hasattr(self.core, "set_idle"):
            try: self.core.set_idle()
            except Exception: pass
