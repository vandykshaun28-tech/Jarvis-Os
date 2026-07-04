import sys
import threading
import psutil
import math
import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPointF, Signal, QObject, QThread, QSize
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QFrame, QGridLayout,
    QStackedWidget, QScrollArea, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QRadialGradient,
    QLinearGradient, QTextCursor, QPixmap
)

try:
    from hud.worker import Worker
    WORKER_OK = True
except Exception:
    WORKER_OK = False

try:
    from voice.voice import JarvisVoice
    VOICE_OK = True
except Exception:
    VOICE_OK = False

try:
    from voice.voice_listener import VoiceListener
    LISTENER_OK = True
except Exception:
    LISTENER_OK = False

# ── COLOURS ─────────────────────────────────────
BG       = "#050d18"
PANEL    = "#071525"
BORDER   = "#0d2137"
ACCENT   = "#00d4ff"
GREEN    = "#00ff88"
YELLOW   = "#ffaa00"
RED      = "#ff4455"
TEXT     = "#a0c8e0"
DIM      = "#2a4a62"
WHITE    = "#e0f0ff"
DARK2    = "#040e1a"

def S(color, size=10, bold=False):
    w = "bold" if bold else "normal"
    return f"color:{color};font-size:{size}px;font-weight:{w};font-family:'Courier New';background:transparent;"

def lbl(text, size=10, color=TEXT, bold=False):
    l = QLabel(text)
    l.setStyleSheet(S(color, size, bold))
    l.setWordWrap(True)
    return l

def hdiv():
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
    f.setFixedHeight(1)
    return f

def vdiv():
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"background:{BORDER};max-width:1px;border:none;")
    f.setFixedWidth(1)
    return f

def make_panel(title=""):
    w = QFrame()
    w.setStyleSheet(f"QFrame{{background:{PANEL};border:1px solid {BORDER};border-radius:6px;}}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(12,10,12,10)
    lay.setSpacing(6)
    if title:
        t = lbl(title.upper(), 8, ACCENT)
        t.setStyleSheet(S(ACCENT,8) + "letter-spacing:3px;")
        lay.addWidget(t)
        lay.addWidget(hdiv())
    return w, lay

def stat_row(key, val, val_color=ACCENT):
    row = QHBoxLayout()
    row.setContentsMargins(0,0,0,0)
    k = lbl(key, 10, TEXT)
    v = lbl(val, 10, val_color, True)
    v.setAlignment(Qt.AlignRight)
    row.addWidget(k)
    row.addStretch()
    row.addWidget(v)
    return row, v

# ── VOICE BRIDGE ────────────────────────────────
class VoiceBridge(QObject):
    wake_signal     = Signal()
    command_signal  = Signal(str)
    idle_signal     = Signal()
    progress_signal = Signal(str)

# ── WORKER BRIDGE ───────────────────────────────
class WorkerBridge(QObject):
    process_signal = Signal(str)
    finished_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None
        if WORKER_OK:
            try:
                self._thread = QThread()
                self._worker = Worker()
                self._worker.moveToThread(self._thread)
                self.process_signal.connect(self._worker.process)
                self._worker.finished.connect(self.finished_signal)
                self._thread.start()
                print("[WorkerBridge] Worker thread started.")
            except Exception as e:
                print(f"[WorkerBridge] Error: {e}")

    def process(self, text: str):
        print(f"[WorkerBridge] process called with text: '{text}' (len={len(text)})")
        if self._worker and self._thread.isRunning():
            self.process_signal.emit(text)
        else:
            self.finished_signal.emit("Brain not available.")

# ── DUST ORB ────────────────────────────────────
class DustOrb(QWidget):
    def __init__(self, size=180):
        super().__init__()
        self.sz = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.mode = "idle"
        self.t = 0.0
        cx = cy = size // 2
        R = size * 0.34
        rng = random.Random(7)
        self.pts = []
        for _ in range(500):
            a = rng.random()*math.pi*2
            r = rng.random()*R
            self.pts.append({"a":a,"r":r,"x":cx+math.cos(a)*r,"y":cy+math.sin(a)*r,
                              "vx":0.0,"vy":0.0,"phase":rng.random()*math.pi*2,
                              "size":rng.random()*2+0.3,"trail":[]})
        t = QTimer(self); t.timeout.connect(self._tick); t.start(33)

    def set_mode(self, m): self.mode = m

    def _tick(self):
        self.t += 0.018
        cx = cy = self.sz // 2
        R = self.sz * 0.34
        for i, p in enumerate(self.pts):
            if self.mode == "idle":
                dr = self.t*0.07+p["phase"]
                tx = cx+math.cos(p["a"]+dr)*p["r"]*(1+math.sin(self.t*0.4+p["phase"])*0.05)
                ty = cy+math.sin(p["a"]+dr)*p["r"]*(1+math.sin(self.t*0.4+p["phase"])*0.05)
                spd = 0.032
            elif self.mode == "listen":
                r2 = p["r"]*(1+math.sin(self.t*2+p["phase"])*0.25)
                tx = cx+math.cos(p["a"]+self.t*0.1)*r2
                ty = cy+math.sin(p["a"]+self.t*0.1)*r2; spd = 0.06
            elif self.mode == "speak":
                wave = math.sin(self.t*1.6+p["r"]*0.08+p["phase"])
                r2 = p["r"]*(0.72+wave*0.28)
                a2 = p["a"]+self.t*0.09+wave*0.12
                tx = cx+math.cos(a2)*r2; ty = cy+math.sin(a2)*r2; spd = 0.05
            else:
                gather = math.sin(self.t*1.4+p["phase"])*0.5+0.5
                r2 = p["r"]*(0.2+gather*0.85)
                a2 = p["a"]-self.t*(0.2+i*0.00015)
                tx = cx+math.cos(a2)*r2; ty = cy+math.sin(a2)*r2; spd = 0.07
            p["vx"]+=(tx-p["x"])*spd; p["vy"]+=(ty-p["y"])*spd
            p["vx"]*=0.83; p["vy"]*=0.83
            p["x"]+=p["vx"]; p["y"]+=p["vy"]
            p["trail"].append((p["x"],p["y"]))
            if len(p["trail"])>2: p["trail"].pop(0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(0,0,self.sz,self.sz,QColor(0,0,0,0))
        cx = cy = self.sz // 2
        for pt in self.pts:
            trail = pt["trail"]
            if len(trail)>=2:
                tc = QColor(160,100,255,28) if self.mode=="think" else QColor(0,200,255,28)
                p.setPen(QPen(tc,pt["size"]*0.5))
                p.drawLine(QPointF(*trail[0]),QPointF(*trail[1]))
            spd = math.hypot(pt["vx"],pt["vy"])
            dist = math.hypot(pt["x"]-cx,pt["y"]-cy)/(self.sz*0.38)
            brite = max(0.0,1-dist*0.3)
            alpha = int(max(18,brite*(107+math.sin(self.t*1.8+pt["phase"])*56))) if self.mode=="speak" else int(max(18,brite*158))
            col = QColor(160,100,255,alpha) if self.mode=="think" else QColor(0,212,255,alpha)
            r = pt["size"]*(1+spd*0.08)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(pt["x"],pt["y"]),r,r)
        p.end()

# ── COSMIC BG ───────────────────────────────────
class CosmicBg(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.t = 0.0
        rng = random.Random(42)
        self.stars = [{"x":rng.random(),"y":rng.random(),"r":rng.random()*1.2+0.2,
                        "phase":rng.random()*math.pi*2,"spd":rng.random()*0.5+0.1} for _ in range(250)]
        self.nebulae = [
            {"rx":0.12,"ry":0.18,"r":220,"h":220,"a":0.04},
            {"rx":0.82,"ry":0.12,"r":190,"h":260,"a":0.03},
            {"rx":0.50,"ry":0.72,"r":240,"h":200,"a":0.035},
            {"rx":0.08,"ry":0.82,"r":170,"h":280,"a":0.025},
            {"rx":0.88,"ry":0.68,"r":200,"h":240,"a":0.032},
        ]
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def _tick(self): self.t+=0.02; self.update()

    def paintEvent(self, event):
        p = QPainter(self); W,H = self.width(),self.height()
        p.fillRect(0,0,W,H,QColor("#050d18"))
        for n in self.nebulae:
            nx,ny = int(n["rx"]*W),int(n["ry"]*H)
            g = QRadialGradient(nx,ny,n["r"])
            h,a = n["h"],n["a"]
            g.setColorAt(0,QColor.fromHsvF(h/360,0.7,0.55,a))
            g.setColorAt(0.55,QColor.fromHsvF(h/360,0.6,0.4,a*0.35))
            g.setColorAt(1,QColor(0,0,0,0))
            p.setBrush(QBrush(g)); p.setPen(Qt.NoPen)
            p.drawEllipse(nx-n["r"],ny-n["r"],n["r"]*2,n["r"]*2)
        for s in self.stars:
            tw = max(0.0,min(1.0,0.25+math.sin(self.t*s["spd"]+s["phase"])*0.75))
            sx,sy = int(s["x"]*W),int(s["y"]*H)
            p.setBrush(QBrush(QColor(200,225,255,int(tw*220)))); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(sx,sy),s["r"],s["r"])
        p.end()

# ── SIDEBAR BUTTON ──────────────────────────────
class SideBtn(QPushButton):
    def __init__(self, icon, text, active=False):
        super().__init__(f"  {icon}   {text}")
        self.setCheckable(True)
        self.setChecked(active)
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self._update_style()
        self.toggled.connect(lambda _: self._update_style())

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(
                f"QPushButton{{background:{BORDER};color:{ACCENT};border:none;"
                f"border-left:3px solid {ACCENT};font-family:'Courier New';"
                f"font-size:11px;font-weight:bold;text-align:left;padding-left:14px;border-radius:0px;}}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton{{background:transparent;color:{TEXT};border:none;"
                f"font-family:'Courier New';font-size:11px;text-align:left;"
                f"padding-left:17px;border-radius:0px;}}"
                f"QPushButton:hover{{background:{BORDER}44;color:{WHITE};}}"
            )

# ── PAGES ───────────────────────────────────────
def make_coming_soon(title, icon="◈"):
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter)
    lay.addStretch()
    ico = lbl(icon, 48, ACCENT); ico.setAlignment(Qt.AlignCenter)
    lay.addWidget(ico)
    lay.addSpacing(16)
    t = lbl(title, 20, WHITE, True); t.setAlignment(Qt.AlignCenter)
    lay.addWidget(t)
    s = lbl("This module is under construction.\nComing in the next build.", 12, DIM)
    s.setAlignment(Qt.AlignCenter); lay.addWidget(s)
    lay.addStretch()
    return w

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12,12,12,12)
        lay.setSpacing(8)

        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(self._overview(), 1)
        top.addWidget(self._orb_panel(), 0)
        top.addWidget(self._agents(), 1)
        lay.addLayout(top, 2)

        bot = QHBoxLayout(); bot.setSpacing(8)
        bot.addWidget(self._tasks_panel(), 1)
        bot.addWidget(self._schedule(), 1)
        bot.addWidget(self._activity(), 1)
        lay.addLayout(bot, 1)

    def _overview(self):
        w,l = make_panel("Overview")
        l.addWidget(lbl("Everything is running smoothly.", 10, GREEN))
        l.addWidget(lbl("All systems operational.", 9, DIM))
        l.addWidget(hdiv())
        for k,v,c in [("AI Agents","6 Active",GREEN),("Tasks Running","0",ACCENT),
                       ("Memories","12",ACCENT),("System Health","100%",GREEN)]:
            r,_ = stat_row(k,v,c); l.addLayout(r)
        l.addStretch(); return w

    def _orb_panel(self):
        w = QFrame(); w.setFixedWidth(240)
        w.setStyleSheet(f"QFrame{{background:{PANEL};border:1px solid {BORDER};border-radius:6px;}}")
        lay = QVBoxLayout(w); lay.setContentsMargins(10,14,10,10); lay.setAlignment(Qt.AlignCenter)
        self.orb = DustOrb(200)
        lay.addWidget(self.orb, alignment=Qt.AlignCenter)
        self.orb_state = lbl("Standing by", 10, ACCENT)
        self.orb_state.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.orb_state)
        stats = QHBoxLayout()
        self.cpu_v = lbl("—",9,GREEN,True); self.ram_v = lbl("—",9,GREEN,True)
        stats.addWidget(lbl("CPU",9,DIM)); stats.addWidget(self.cpu_v)
        stats.addSpacing(12)
        stats.addWidget(lbl("RAM",9,DIM)); stats.addWidget(self.ram_v)
        lay.addLayout(stats); return w

    def _agents(self):
        w,l = make_panel("Active AI Agents")
        l.addWidget(lbl("6 Active", 9, GREEN))
        l.addWidget(hdiv())
        for name,col in [("Brain Agent",GREEN),("Memory Agent",GREEN),("Web Agent",GREEN),
                          ("Task Agent",GREEN),("Voice Agent",GREEN),("Obsidian Agent",YELLOW)]:
            r = QHBoxLayout()
            r.addWidget(lbl(f"◈  {name}",10,TEXT))
            r.addStretch()
            r.addWidget(lbl("Online" if col==GREEN else "Pending",9,col))
            l.addLayout(r)
        l.addStretch(); return w

    def _tasks_panel(self):
        w,l = make_panel("Tasks")
        self.task_lbl = lbl("0 Pending",9,ACCENT); l.addWidget(self.task_lbl)
        l.addWidget(hdiv())
        self.task_area = QVBoxLayout(); self.task_area.setSpacing(3)
        self.task_area.addWidget(lbl("No pending tasks, sir.",10,DIM))
        l.addLayout(self.task_area); l.addStretch(); return w

    def _schedule(self):
        w,l = make_panel("Today's Schedule")
        for hr,task in [("07:00","Morning briefing"),("12:00","Midday check"),("18:00","Evening summary")]:
            r = QHBoxLayout()
            r.addWidget(lbl(hr,9,ACCENT))
            r.addSpacing(8)
            r.addWidget(lbl(task,10,TEXT))
            r.addStretch(); l.addLayout(r)
        l.addStretch(); return w

    def _activity(self):
        w,l = make_panel("Recent Activity")
        self.act_lay = QVBoxLayout(); self.act_lay.setSpacing(3)
        for m in ["JARVIS online.","Memory loaded.","Obsidian connected."]:
            self.act_lay.addWidget(lbl(f"◎  {m}",9,TEXT))
        l.addLayout(self.act_lay); l.addStretch(); return w

    def add_activity(self, msg):
        lbl_w = lbl(f"◎  {msg}", 9, TEXT)
        self.act_lay.insertWidget(0, lbl_w)
        if self.act_lay.count() > 6:
            item = self.act_lay.takeAt(self.act_lay.count()-1)
            if item.widget(): item.widget().deleteLater()

class TasksPage(QWidget):
    def __init__(self):
        super().__init__(); self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self); lay.setContentsMargins(12,12,12,12); lay.setSpacing(8)
        w,l = make_panel("Task Manager")
        l.addWidget(lbl("Manage your tasks — say 'add task X' or 'show tasks'",10,TEXT))
        l.addWidget(hdiv())
        self.task_lay = QVBoxLayout(); self.task_lay.setSpacing(4)
        self.task_lay.addWidget(lbl("No tasks yet. Say 'add task' to get started.",10,DIM))
        l.addLayout(self.task_lay); l.addStretch()
        lay.addWidget(w); lay.addStretch()

    def refresh(self, tasks):
        while self.task_lay.count():
            item = self.task_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not tasks:
            self.task_lay.addWidget(lbl("No tasks. Say 'add task X' to create one.",10,DIM))
        else:
            for t in tasks:
                icon = "✓" if t.get("status")=="done" else "○"
                col  = DIM if t.get("status")=="done" else TEXT
                pri  = t.get("priority","normal").upper()
                pri_col = RED if pri=="HIGH" else (YELLOW if pri=="NORMAL" else GREEN)
                row = QHBoxLayout()
                row.addWidget(lbl(f"{icon}  {t['title']}",10,col))
                row.addStretch()
                row.addWidget(lbl(pri,8,pri_col))
                self.task_lay.addLayout(row)

class MemoryPage(QWidget):
    def __init__(self):
        super().__init__(); self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self); lay.setContentsMargins(12,12,12,12); lay.setSpacing(8)
        w,l = make_panel("Memory Vault")
        l.addWidget(lbl("Say 'remember X' to save a memory. Say 'show memories' to list them.",10,TEXT))
        l.addWidget(hdiv())
        self.mem_lay = QVBoxLayout(); self.mem_lay.setSpacing(4)
        l.addLayout(self.mem_lay); l.addStretch()
        lay.addWidget(w); lay.addStretch()

    def refresh(self, facts):
        while self.mem_lay.count():
            item = self.mem_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for f in facts:
            self.mem_lay.addWidget(lbl(f"◈  {f}",10,TEXT))
        if not facts:
            self.mem_lay.addWidget(lbl("Memory banks empty.",10,DIM))

# ── MAIN HUD ────────────────────────────────────
class JarvisHUD(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS — AI Command Centre")
        self.resize(1440, 880)
        self.setMinimumSize(1200,700)
        self.setStyleSheet(f"background:{BG};color:{TEXT};font-family:'Courier New';")
        self.start_time = datetime.now()
        self.voice  = JarvisVoice() if VOICE_OK else None

        # Progress bridge for thread-safe research updates
        self._pb = VoiceBridge()
        self._pb.progress_signal.connect(self._on_progress)
        self._pb.command_signal.connect(self._on_research_complete)

        # Worker bridge
        self.worker = WorkerBridge()
        self.worker.finished_signal.connect(self._on_reply)

        self._build()
        self._wire_voice()

        # Delay callback injection so worker thread has time to start
        QTimer.singleShot(3000, self._inject_callbacks)

        tick = QTimer(self); tick.timeout.connect(self._tick); tick.start(1000)

    def _inject_callbacks(self):
        """Give brain a way to send progress updates to the chat."""
        try:
            if self.worker._worker and hasattr(self.worker._worker, 'brain'):
                brain = self.worker._worker.brain
                if brain:
                    brain.chat_callback    = self._pb.progress_signal.emit
                    brain.voice_callback   = self.voice.speak if self.voice else None
                    if hasattr(brain, 'researcher') and brain.researcher:
                        brain.researcher.on_progress = self._pb.progress_signal.emit
                        brain.researcher.on_complete = self._pb.command_signal.emit
                    if hasattr(brain, 'task_manager') and brain.task_manager:
                        brain.task_manager.chat_callback  = self._pb.progress_signal.emit
                        brain.task_manager.voice_callback = self.voice.speak if self.voice else None
                    if hasattr(brain, 'agent') and brain.agent:
                        brain.agent.chat_callback  = self._pb.progress_signal.emit
                        brain.agent.voice_callback = self.voice.speak if self.voice else None
                    print("[HUD] Callbacks injected into brain.")
        except Exception as e:
            print(f"[HUD] Callback injection: {e}")

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.bg = CosmicBg(self); self.bg.setGeometry(0,0,1440,880); self.bg.lower()
        root.addWidget(self._topbar())
        root.addWidget(hdiv())
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        body.addWidget(self._sidebar())
        body.addWidget(vdiv())
        body.addWidget(self._workspace(), 1)
        body.addWidget(vdiv())
        body.addWidget(self._console())
        root.addLayout(body, 1)

    # ── TOP BAR ─────────────────────────────────
    def _topbar(self):
        bar = QWidget(); bar.setFixedHeight(56)
        bar.setStyleSheet(f"background:{PANEL};")
        lay = QHBoxLayout(bar); lay.setContentsMargins(20,0,20,0); lay.setSpacing(0)

        logo = lbl("⬡  JARVIS", 18, ACCENT, True)
        logo.setStyleSheet(S(ACCENT,18,True)+"letter-spacing:5px;")
        sub  = lbl("AI COMMAND CENTRE", 8, DIM)
        sub.setStyleSheet(S(DIM,8)+"letter-spacing:3px;")
        ll = QVBoxLayout(); ll.setSpacing(0); ll.addWidget(logo); ll.addWidget(sub)
        lay.addLayout(ll); lay.addSpacing(24)

        for txt,col in [("● SYSTEM OPTIMAL",GREEN),("● NETWORK SECURE",GREEN),("● VOICE ACTIVE",GREEN)]:
            p = lbl(txt,9,col)
            p.setStyleSheet(S(col,9)+f"border:1px solid {col}55;border-radius:10px;padding:3px 10px;background:{col}11;")
            lay.addWidget(p); lay.addSpacing(12)

        lay.addStretch()

        for label,attr in [("MEMORY","top_mem"),("CPU","top_cpu"),("UPTIME","top_upt")]:
            col = QVBoxLayout(); col.setSpacing(0); col.setAlignment(Qt.AlignCenter)
            k = lbl(label,8,DIM); k.setStyleSheet(S(DIM,8)+"letter-spacing:2px;")
            v = lbl("—",11,ACCENT,True)
            setattr(self,attr,v)
            col.addWidget(k,alignment=Qt.AlignCenter); col.addWidget(v,alignment=Qt.AlignCenter)
            lay.addLayout(col); lay.addSpacing(24)

        self.top_clock = lbl("00:00:00",20,WHITE,True)
        self.top_date  = lbl("—",8,DIM)
        cc = QVBoxLayout(); cc.setSpacing(0)
        cc.addWidget(self.top_clock,alignment=Qt.AlignRight)
        cc.addWidget(self.top_date,alignment=Qt.AlignRight)
        lay.addLayout(cc); lay.addSpacing(16)

        wel = lbl("Welcome back,  SHAUN",10,TEXT); lay.addWidget(wel)
        return bar

    # ── SIDEBAR ──────────────────────────────────
    def _sidebar(self):
        w = QWidget(); w.setFixedWidth(180)
        w.setStyleSheet(f"background:{PANEL};")
        lay = QVBoxLayout(w); lay.setContentsMargins(0,12,0,12); lay.setSpacing(2)

        self._nav_btns = []
        pages = [
            ("⊞","DASHBOARD",0),("◈","AI AGENTS",1),("✓","TASKS",2),
            ("◉","MEMORY",3),("⊙","KNOWLEDGE",4),("◎","CALENDAR",5),
            ("⊕","WEB",6),("⊗","FILES",7),("◈","SETTINGS",8),
        ]
        for icon,text,idx in pages:
            btn = SideBtn(icon,text,idx==0)
            btn.clicked.connect(lambda _,i=idx,b=btn: self._nav(i,b))
            self._nav_btns.append(btn)
            lay.addWidget(btn)

        lay.addStretch()
        lay.addWidget(hdiv())

        vc = lbl("VOICE CONTROL",8,DIM)
        vc.setStyleSheet(S(DIM,8)+"letter-spacing:2px;padding:4px 16px;")
        lay.addWidget(vc)
        self.voice_lbl = lbl("〰 Listening...",9,GREEN)
        self.voice_lbl.setStyleSheet(S(GREEN,9)+"padding-left:16px;")
        lay.addWidget(self.voice_lbl)
        lay.addSpacing(8)

        orb_lbl = lbl("⬡ JARVIS AI",10,ACCENT,True)
        orb_lbl.setAlignment(Qt.AlignCenter); lay.addWidget(orb_lbl)
        sub = lbl("How can I\nhelp you today?",9,DIM)
        sub.setAlignment(Qt.AlignCenter); lay.addWidget(sub)
        lay.addSpacing(8)
        return w

    def _nav(self, idx, clicked_btn):
        for btn in self._nav_btns:
            btn.setChecked(btn is clicked_btn)
            btn._update_style()
        self.stack.setCurrentIndex(idx)

    # ── WORKSPACE ────────────────────────────────
    def _workspace(self):
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;")

        self.dash = DashboardPage()
        self.stack.addWidget(self.dash)                          # 0 dashboard
        self.stack.addWidget(make_coming_soon("AI Agents","◈"))  # 1
        self.tasks_page = TasksPage()
        self.stack.addWidget(self.tasks_page)                    # 2 tasks
        self.mem_page = MemoryPage()
        self.stack.addWidget(self.mem_page)                      # 3 memory
        self.stack.addWidget(make_coming_soon("Knowledge","⊙"))  # 4
        self.stack.addWidget(make_coming_soon("Calendar","◎"))   # 5
        self.stack.addWidget(make_coming_soon("Web Search","⊕")) # 6
        self.stack.addWidget(make_coming_soon("Files","⊗"))      # 7
        self.stack.addWidget(make_coming_soon("Settings","◈"))   # 8
        return self.stack

    # ── CONSOLE ──────────────────────────────────
    def _console(self):
        w = QWidget(); w.setFixedWidth(320)
        w.setStyleSheet(f"background:{PANEL};")
        lay = QVBoxLayout(w); lay.setContentsMargins(12,12,12,12); lay.setSpacing(8)

        t = lbl("JARVIS CONSOLE",9,ACCENT)
        t.setStyleSheet(S(ACCENT,9)+"letter-spacing:3px;")
        lay.addWidget(t); lay.addWidget(hdiv())

        self.chat = QTextEdit(); self.chat.setReadOnly(True)
        self.chat.setStyleSheet(
            f"QTextEdit{{background:{DARK2};border:1px solid {BORDER};border-radius:4px;"
            f"color:{TEXT};font-family:'Courier New';font-size:11px;padding:8px;}}"
        )
        self.chat.append(f'<span style="color:{DIM};">// JARVIS v20 online</span>')
        self.chat.append(f'<span style="color:{ACCENT};">JARVIS: Good day, sir. All systems nominal.</span>')
        lay.addWidget(self.chat,1)

        self.mode_lbl = lbl("● IDLE",9,GREEN); lay.addWidget(self.mode_lbl)

        # Research status indicator
        self.research_lbl = lbl("",9,YELLOW)
        self.research_lbl.setStyleSheet(
            S(YELLOW,9) + f"background:{YELLOW}11;border:1px solid {YELLOW}44;"
            f"border-radius:4px;padding:3px 8px;"
        )
        self.research_lbl.hide()
        lay.addWidget(self.research_lbl)

        row = QHBoxLayout()
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Type a command, sir...")
        self.inp.setStyleSheet(
            f"QLineEdit{{background:{DARK2};border:1px solid {BORDER};border-radius:4px;"
            f"color:{ACCENT};font-family:'Courier New';font-size:11px;padding:8px;}}"
            f"QLineEdit:focus{{border:1px solid {ACCENT}55;}}"
        )
        self.inp.returnPressed.connect(self._send)
        btn = QPushButton("EXECUTE"); btn.setFixedWidth(80)
        btn.setStyleSheet(
            f"QPushButton{{background:{BORDER};border:1px solid {ACCENT}55;color:{ACCENT};"
            f"font-family:'Courier New';font-size:9px;letter-spacing:1px;padding:8px;border-radius:4px;}}"
            f"QPushButton:hover{{background:{ACCENT}22;}}"
        )
        btn.clicked.connect(self._send)
        row.addWidget(self.inp); row.addWidget(btn); lay.addLayout(row)
        lay.addWidget(hdiv())

        mon = lbl("SYSTEM MONITOR",9,ACCENT)
        mon.setStyleSheet(S(ACCENT,9)+"letter-spacing:3px;"); lay.addWidget(mon)
        grid = QGridLayout(); grid.setSpacing(4)
        for i,(k,attr,col) in enumerate([("Brain","mon_brain",GREEN),("Voice","mon_voice",GREEN),
                                          ("Claude","mon_claude",GREEN),("Obsidian","mon_obs",YELLOW)]):
            mk = lbl(k,9,TEXT); mv = lbl("● Online" if col==GREEN else "● Pending",9,col)
            setattr(self,attr,mv)
            grid.addWidget(mk,i//2,(i%2)*2); grid.addWidget(mv,i//2,(i%2)*2+1)
        lay.addLayout(grid)
        lay.addWidget(hdiv())

        notif = lbl("NOTIFICATIONS",9,ACCENT)
        notif.setStyleSheet(S(ACCENT,9)+"letter-spacing:3px;"); lay.addWidget(notif)
        self.notif_lay = QVBoxLayout(); self.notif_lay.setSpacing(2)
        lay.addLayout(self.notif_lay)
        return w

    # ── VOICE ─────────────────────────────────
    def _wire_voice(self):
        if LISTENER_OK:
            try:
                self._vb = VoiceBridge()
                self._vb.wake_signal.connect(self._on_wake)
                self._vb.command_signal.connect(self._process_voice)
                self._vb.idle_signal.connect(lambda: self._set_mode("idle"))
                self.listener = VoiceListener(
                    on_command=self._vb.command_signal.emit,
                    on_wake=self._vb.wake_signal.emit,
                    on_idle=self._vb.idle_signal.emit,
                )
                self.listener.start()
            except Exception as e:
                print(f"Listener error: {e}")

    # ── LOGIC ──────────────────────────────────
    def _send(self):
        text = self.inp.text().strip()
        print(f"[HUD] _send() called with text: '{text}' (len={len(text)})")
        if not text:
            return
        self._chat_add(f'<span style="color:{GREEN};">YOU: {text}</span>')
        self.inp.clear()
        self._set_mode("think")
        self.worker.process(text)

    def _on_progress(self, msg: str):
        self._chat_add(f'<span style="color:{YELLOW};">{msg}</span>')
        self._notif(msg[:40], YELLOW)
        self.research_lbl.setText(f"🔬 STUDYING: {msg[:50]}...")
        self.research_lbl.show()
        self._set_mode("think")

    def _on_research_complete(self, msg: str):
        self._chat_add(f'<span style="color:{GREEN};">✅ JARVIS: {msg}</span>')
        self._notif("Research complete!", GREEN)
        self.research_lbl.setText("✅ Research complete — knowledge saved")
        self.research_lbl.setStyleSheet(
            S(GREEN,9) + f"background:{GREEN}11;border:1px solid {GREEN}44;"
            f"border-radius:4px;padding:3px 8px;"
        )
        self.research_lbl.show()
        self._set_mode("idle")
        QTimer.singleShot(8000, self.research_lbl.hide)
        if self.voice:
            threading.Thread(
                target=self.voice.speak,
                args=("Research complete, sir. Knowledge saved permanently.",),
                daemon=True
            ).start()

    def _on_reply(self, reply):
        self._chat_add(f'<span style="color:{ACCENT};">JARVIS: {reply}</span>')
        self.dash.add_activity(reply[:45]+"...")
        self._notif(f"Response: {reply[:30]}...")
        self._set_mode("speak")
        if self.voice:
            def speak_idle():
                self.voice.speak(reply)
                self._set_mode("idle")
            threading.Thread(target=speak_idle,daemon=True).start()
        else:
            QTimer.singleShot(2000, lambda: self._set_mode("idle"))

    def _on_wake(self):
        self._set_mode("listen")
        self._chat_add(f'<span style="color:{GREEN}55;">🎤 Listening...</span>')

    def _process_voice(self, text):
        self._chat_add(f'<span style="color:{GREEN};">🎤 YOU: {text}</span>')
        self._set_mode("think")
        self.worker.process(text)

    def _set_mode(self, mode):
        labels = {"idle":"Standing by","listen":"Listening...","speak":"Speaking...","think":"Processing..."}
        colors = {"idle":GREEN,"listen":ACCENT,"speak":ACCENT,"think":YELLOW}
        self.dash.orb.set_mode(mode)
        self.dash.orb_state.setText(labels.get(mode,mode.title()))
        col = colors.get(mode,GREEN)
        self.mode_lbl.setText(f"● {mode.upper()}")
        self.mode_lbl.setStyleSheet(S(col,9))

    def _chat_add(self, html):
        self.chat.append(html)
        self.chat.moveCursor(QTextCursor.End)
        self.chat.ensureCursorVisible()

    def _notif(self, msg, color=ACCENT):
        l = lbl(f"▸ {msg}",9,color)
        self.notif_lay.insertWidget(0,l)
        if self.notif_lay.count()>4:
            item = self.notif_lay.takeAt(self.notif_lay.count()-1)
            if item.widget(): item.widget().deleteLater()

    # ── TICK ───────────────────────────────────
    def _tick(self):
        now = datetime.now()
        self.top_clock.setText(now.strftime("%H:%M:%S"))
        self.top_date.setText(now.strftime("%A, %d %B %Y").upper())
        elapsed = int((now-self.start_time).total_seconds())
        h,rem = divmod(elapsed,3600); m,s = divmod(rem,60)
        self.top_upt.setText(f"{h:02d}h {m:02d}m")
        cpu = int(psutil.cpu_percent())
        ram = int(psutil.virtual_memory().percent)
        self.dash.cpu_v.setText(f"{cpu}%")
        self.dash.ram_v.setText(f"{ram}%")
        self.top_cpu.setText(f"{cpu}%")
        self.top_mem.setText(f"{ram}%")

    def resizeEvent(self, e):
        self.bg.setGeometry(0,0,self.width(),self.height())
        super().resizeEvent(e)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = JarvisHUD(); w.show()
    sys.exit(app.exec())