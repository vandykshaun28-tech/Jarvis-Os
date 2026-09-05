"""
AI Agents page — WATCH ALLISON'S AGENTS WORK.
Live status cards for every background agent + a live activity feed +
a study progress bar, refreshed every second. Themed to Allison's
violet palette (reads pal() so it recolours with the app).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QProgressBar,
)
from PySide6.QtCore import Qt, QTimer


def _pal():
    try:
        from ui.styles.theme_manager import pal
        return pal()
    except Exception:
        return {"accent": "#b06bff", "panel": "#160f28", "line": "#2d1f4a",
                "text": "#f1ecfa", "text2": "#a394c4", "dim": "#8f83ad"}


STATUS_COLORS = {
    "running":        "#22e39a",
    "stopped":        "#8f83ad",
    "error":          "#fb5e8b",
    "not_configured": "#f5a623",
}


class AgentCard(QFrame):

    def __init__(self):
        super().__init__()
        p = _pal()
        self.setStyleSheet(
            f"QFrame{{background:{p['panel']};border:1px solid {p['line']};"
            "border-radius:12px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.name = QLabel("—")
        self.name.setStyleSheet(
            f"color:{p['text']};font-size:15px;font-weight:700;border:none;")
        self.state = QLabel("—")
        top.addWidget(self.name)
        top.addStretch()
        top.addWidget(self.state)
        lay.addLayout(top)

        self.desc = QLabel("")
        self.desc.setStyleSheet(
            f"color:{p['text2']};font-size:11px;border:none;")
        lay.addWidget(self.desc)

        self.events = QLabel("")
        self.events.setStyleSheet(
            f"color:{p['text']};font-size:11px;border:none;font-family:Consolas;")
        self.events.setWordWrap(True)
        lay.addWidget(self.events)

    def update_from(self, snap):
        self.name.setText(snap["name"])
        color = STATUS_COLORS.get(snap["status"], "#a394c4")
        label = snap["status"].replace("_", " ").upper()
        self.state.setText(f"● {label}")
        self.state.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:700;border:none;")
        self.desc.setText(snap["description"])
        lines = [f"{t}  {m}" for t, m in snap["events"][:6]]
        self.events.setText("\n".join(lines) or "Idle — waiting for its next cycle.")


class AgentsPage(QWidget):
    """provider: () -> list of agent snapshot dicts
       activity_provider: () -> (current_activity, [ledger entries])
       study_provider: () -> {topic, percent, stage, active}"""

    def __init__(self, provider=None, activity_provider=None,
                 study_provider=None):
        super().__init__()
        self.provider = provider or (lambda: [])
        self.activity_provider = activity_provider
        self.study_provider = study_provider
        self.cards = {}
        self._beat = 0
        p = _pal()
        self.setStyleSheet("background:transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        title = QLabel("AI AGENTS  ·  WATCH THEM WORK")
        title.setStyleSheet(
            f"color:{p['accent']};font-size:13px;font-weight:700;"
            "letter-spacing:3px;border:none;")
        root.addWidget(title)

        # ── STUDY progress bar — visible learning ────────────────────
        self.study_card = QFrame()
        self.study_card.setStyleSheet(
            f"QFrame{{background:{p['panel']};border:1px solid {p['accent']}55;"
            "border-radius:12px;}")
        slay = QVBoxLayout(self.study_card)
        slay.setContentsMargins(16, 12, 16, 12)
        slay.setSpacing(6)
        self.study_title = QLabel("STUDY")
        self.study_title.setStyleSheet(
            f"color:{p['accent']};font-size:9px;font-weight:700;"
            "letter-spacing:2px;border:none;")
        slay.addWidget(self.study_title)
        self.study_label = QLabel("Not studying anything right now.")
        self.study_label.setStyleSheet(
            f"color:{p['text']};font-size:13px;font-weight:600;border:none;")
        self.study_label.setWordWrap(True)
        slay.addWidget(self.study_label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFixedHeight(18)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:{p['line']};border:none;border-radius:9px;"
            f"color:{p['text']};font-size:10px;font-weight:700;text-align:center;}}"
            f"QProgressBar::chunk{{background:{p['accent']};border-radius:9px;}}")
        slay.addWidget(self.bar)
        self.study_stage = QLabel("")
        self.study_stage.setStyleSheet(
            f"color:{p['text2']};font-size:11px;border:none;")
        slay.addWidget(self.study_stage)
        self.study_card.hide()
        root.addWidget(self.study_card)

        # ── verified live activity ───────────────────────────────────
        self.act_card = QFrame()
        self.act_card.setStyleSheet(
            f"QFrame{{background:{p['panel']};border:1px solid {p['accent']}44;"
            "border-radius:12px;}")
        alay = QVBoxLayout(self.act_card)
        alay.setContentsMargins(16, 12, 16, 12)
        at = QLabel("LIVE ACTIVITY  (verified — from real tool executions)")
        at.setStyleSheet(f"color:{p['accent']};font-size:9px;font-weight:700;"
                         "letter-spacing:2px;border:none;")
        alay.addWidget(at)
        self.act_now = QLabel("—")
        self.act_now.setStyleSheet(
            f"color:{p['text']};font-size:13px;font-weight:600;border:none;")
        self.act_now.setWordWrap(True)
        alay.addWidget(self.act_now)
        self.act_log = QLabel("")
        self.act_log.setStyleSheet(
            f"color:{p['text']};font-size:11px;border:none;font-family:Consolas;")
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
        self.timer.start(1000)
        self.refresh()

    def refresh(self):
        self._beat = (self._beat + 1) % 4
        pulse = "●" + "·" * self._beat

        # study progress
        if self.study_provider:
            try:
                sp = self.study_provider() or {}
            except Exception:
                sp = {}
            if sp.get("topic") and (sp.get("active") or sp.get("percent")):
                self.study_card.show()
                pct = int(sp.get("percent", 0))
                self.bar.setValue(pct)
                if sp.get("active"):
                    self.study_label.setText(f"{pulse}  Studying: {sp['topic']}")
                else:
                    self.study_label.setText(f"✓  Finished studying: {sp['topic']}")
                self.study_stage.setText(str(sp.get("stage", "")).capitalize())
            else:
                self.study_card.hide()

        # live activity
        if self.activity_provider:
            try:
                now, entries = self.activity_provider()
                if now and now not in ("idle", "unknown", "starting up"):
                    self.act_now.setText(f"{pulse}  BUSY: {now}")
                else:
                    self.act_now.setText("● IDLE — standing by")
                lines = []
                for e in entries[:8]:
                    mark = "✓" if e.get("status") == "ok" else "✗"
                    lines.append(f"{e['time']} {mark} {e['action']}"
                                 + (f" — {e['detail']}" if e.get("detail") else ""))
                self.act_log.setText("\n".join(lines) or
                                     "Nothing done yet this session.")
            except Exception:
                pass

        # agent cards
        try:
            snaps = self.provider() or []
        except Exception:
            snaps = []
        if not snaps and not self.cards:
            # never look broken while the brain is still booting
            self.act_now.setText(self.act_now.text() or "● Bringing agents online…")
        for snap in snaps:
            card = self.cards.get(snap["name"])
            if card is None:
                card = AgentCard()
                self.cards[snap["name"]] = card
                self.list_lay.insertWidget(self.list_lay.count() - 1, card)
            card.update_from(snap)
