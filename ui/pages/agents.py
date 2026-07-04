"""
AI Agents page — live status cards for every background agent,
refreshed every 2 seconds from the agent manager.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer

STATUS_COLORS = {
    "running":        "#2ecc71",
    "stopped":        "#5a8bb0",
    "error":          "#ff5566",
    "not_configured": "#f5a623",
}


class AgentCard(QFrame):

    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            "QFrame{background:#0a1420;border:1px solid #12324a;"
            "border-radius:12px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.name = QLabel("—")
        self.name.setStyleSheet(
            "color:#e8f6ff;font-size:15px;font-weight:700;border:none;")
        self.state = QLabel("—")
        top.addWidget(self.name)
        top.addStretch()
        top.addWidget(self.state)
        lay.addLayout(top)

        self.desc = QLabel("")
        self.desc.setStyleSheet("color:#5a8bb0;font-size:11px;border:none;")
        lay.addWidget(self.desc)

        self.events = QLabel("")
        self.events.setStyleSheet(
            "color:#c7e3f5;font-size:11px;border:none;font-family:Consolas;")
        self.events.setWordWrap(True)
        lay.addWidget(self.events)

    def update_from(self, snap):
        self.name.setText(snap["name"])
        color = STATUS_COLORS.get(snap["status"], "#7ba7c2")
        label = snap["status"].replace("_", " ").upper()
        self.state.setText(f"● {label}")
        self.state.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:700;border:none;")
        self.desc.setText(snap["description"])
        lines = [f"{t}  {m}" for t, m in snap["events"][:6]]
        self.events.setText("\n".join(lines) or "No events yet.")


class AgentsPage(QWidget):
    """provider: () -> list of agent snapshot dicts
       activity_provider: () -> (current_activity, [ledger entries])"""

    def __init__(self, provider=None, activity_provider=None):
        super().__init__()
        self.provider = provider or (lambda: [])
        self.activity_provider = activity_provider
        self.cards = {}
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        title = QLabel("AI AGENTS")
        title.setStyleSheet(
            "color:#22d3ee;font-size:13px;font-weight:700;"
            "letter-spacing:3px;border:none;")
        root.addWidget(title)

        # verified activity ledger — what JARVIS is ACTUALLY doing
        self.act_card = QFrame()
        self.act_card.setStyleSheet(
            "QFrame{background:#0a1420;border:1px solid #22d3ee44;"
            "border-radius:12px;}")
        alay = QVBoxLayout(self.act_card)
        alay.setContentsMargins(16, 12, 16, 12)
        at = QLabel("LIVE ACTIVITY  (verified — from real tool executions)")
        at.setStyleSheet("color:#22d3ee;font-size:9px;font-weight:700;"
                         "letter-spacing:2px;border:none;")
        alay.addWidget(at)
        self.act_now = QLabel("—")
        self.act_now.setStyleSheet(
            "color:#e8f6ff;font-size:13px;font-weight:600;border:none;")
        self.act_now.setWordWrap(True)
        alay.addWidget(self.act_now)
        self.act_log = QLabel("")
        self.act_log.setStyleSheet(
            "color:#c7e3f5;font-size:11px;border:none;font-family:Consolas;")
        self.act_log.setWordWrap(True)
        alay.addWidget(self.act_log)
        root.addWidget(self.act_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;border:none;")
        scroll.viewport().setStyleSheet("background:transparent;")
        root.addWidget(scroll, 1)

        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        self.list_lay = QVBoxLayout(inner)
        self.list_lay.setSpacing(10)
        self.list_lay.addStretch()
        scroll.setWidget(inner)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def refresh(self):
        if self.activity_provider:
            try:
                now, entries = self.activity_provider()
                self.act_now.setText(
                    "● IDLE — standing by" if now == "idle"
                    else f"● BUSY: {now}")
                lines = []
                for e in entries[:8]:
                    mark = "✓" if e.get("status") == "ok" else "✗"
                    lines.append(f"{e['time']} {mark} {e['action']}"
                                 + (f" — {e['detail']}" if e.get("detail") else ""))
                self.act_log.setText("\n".join(lines) or
                                     "Nothing done yet this session.")
            except Exception:
                pass
        try:
            snaps = self.provider() or []
        except Exception:
            snaps = []
        for snap in snaps:
            card = self.cards.get(snap["name"])
            if card is None:
                card = AgentCard()
                self.cards[snap["name"]] = card
                self.list_lay.insertWidget(self.list_lay.count() - 1, card)
            card.update_from(snap)
