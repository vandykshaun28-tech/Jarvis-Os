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
        self._drag = None
        self.setStyleSheet(
            f"QFrame{{background:rgba(8,17,28,0.86);border:1px solid {LINE};"
            f"border-radius:12px;}}")
        self.setFixedWidth(200)
        self.setMaximumHeight(78)
        self.setCursor(Qt.OpenHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet(f"color:{DIM};font-size:8px;font-weight:700;"
                        f"letter-spacing:2px;border:none;background:transparent;")
        lay.addWidget(t)
        self.value = QLabel("—")
        self.value.setWordWrap(True)
        self.value.setStyleSheet(f"color:{CYAN};font-size:12px;font-weight:600;"
                                 f"border:none;background:transparent;")
        lay.addWidget(self.value)
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{DIM};font-size:9px;border:none;"
                               f"background:transparent;")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)

    # ── drag anywhere ────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            self.raise_()

    def mouseMoveEvent(self, event):
        if self._drag is not None and self.parentWidget():
            new = self.mapToParent(event.position().toPoint() - self._drag)
            par = self.parentWidget()
            x = max(0, min(new.x(), par.width() - self.width()))
            y = max(0, min(new.y(), par.height() - self.height()))
            self.move(x, y)

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def set(self, value, sub="", color=CYAN):
        v = str(value)
        if len(v) > 60:
            v = v[:57] + "…"
        self.value.setText(v)
        self.value.setStyleSheet(f"color:{color};font-size:12px;font-weight:600;"
                                 f"border:none;background:transparent;")
        self.sub.setText(sub[:50])


class ListenPill(QFrame):
    """Live-mic pill. HIDDEN on standby — it only appears while JARVIS
    is actually capturing your command (after 'hey jarvis'), or stays
    up in red if the microphone is offline."""

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
        self.text = QLabel("listening, sir…")
        self.text.setStyleSheet(f"color:{DIM};font-size:12px;border:none;"
                                f"background:transparent;")
        lay.addWidget(self.text)
        self._t = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()                       # standby = invisible

    def _tick(self):
        self._t += 1
        glyphs = "▁▂▃▄▅▆"
        s = "".join(glyphs[int((math.sin(self._t * 0.9 + i) + 1) * 2.6)]
                    for i in range(5))
        self.bars.setText(s)

    def set_state(self, state, detail=""):
        if state == "offline":
            self._timer.stop()
            self.bars.setText("▁▁▁▁▁")
            self.bars.setStyleSheet(f"color:{RED};font-size:13px;border:none;"
                                    f"background:transparent;")
            self.text.setText(detail or "microphone offline — type 'voice status'")
            self.show()
        elif state == "listening":
            self.bars.setStyleSheet(f"color:{CYAN};font-size:13px;border:none;"
                                    f"background:transparent;")
            self.text.setText("listening, sir…")
            self._timer.start(120)
            self.show()
            self.raise_()
        else:                              # "hidden" / standby
            self._timer.stop()
            self.hide()


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

        # floating stage cards — free children of the orb, draggable
        # anywhere on the interface (not locked in a layout)
        self.card_now    = StageCard("NOW")
        self.card_pnl    = StageCard("PAPER P&L")
        self.card_thought = StageCard("LAST THOUGHT")
        self._cards = [self.card_now, self.card_pnl, self.card_thought]
        y = 16
        for c in self._cards:
            c.setParent(self)
            c.move(16, y)
            c.show()
            c.raise_()
            y += 88

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
            self._refresh_now()
            self._refresh_memories()
        except Exception:
            pass

    def _refresh_memories(self):
        """One gold neuron per permanent memory — the brain fills up
        with what JARVIS has learned."""
        get = self.providers.get("memories")
        if not get:
            return
        try:
            n = int(get() or 0)
        except Exception:
            return
        if hasattr(self.core, "set_memory_count"):
            self.core.set_memory_count(n)

    def _refresh_now(self):
        get = self.providers.get("activity")
        if not get:
            return
        now, _ = get()
        if now and now not in ("idle", "unknown", "starting up"):
            self.card_now.set(now[:70], "live — from the activity ledger",
                              "#f5a623")
            # the brain itself shows WORKING — with what he's busy on
            if hasattr(self.core, "set_working"):
                try:
                    self.core.set_working(now)
                except Exception:
                    pass
        elif getattr(self.core, "mode", "") == "working":
            # work finished and nothing new started — back to standby
            try:
                self.core.set_idle()
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
        elif not getattr(self, "_listening_live", False):
            self.pill.set_state("hidden")
        # while actively listening, set_listening() drives the pill

    # ── live mic state from controller (wake word → capture → idle) ──
    def set_listening(self, on: bool):
        self._listening_live = bool(on)
        get = self.providers.get("listener")
        listener = get() if get else None
        if listener is None:
            self.pill.set_state("offline")
        else:
            self.pill.set_state("listening" if on else "hidden")

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
