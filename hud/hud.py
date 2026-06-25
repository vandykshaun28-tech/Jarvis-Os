import sys
import threading
import psutil
import math
import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QPointF, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QWidget, QTextEdit, QPushButton,
    QLineEdit, QLabel, QVBoxLayout, QHBoxLayout,
    QFrame
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QTextCursor
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


# ─────────────────────────────────────────────
#  VOICE BRIDGE — safely crosses thread boundary
# ─────────────────────────────────────────────
class VoiceBridge(QObject):
    wake_signal    = Signal()
    command_signal = Signal(str)
    idle_signal    = Signal()


# ─────────────────────────────────────────────
#  COSMIC BACKGROUND
# ─────────────────────────────────────────────
class CosmicBackground(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.t = 0.0

        rng = random.Random(42)
        self.stars = [
            {
                "x": rng.random(),
                "y": rng.random(),
                "r": rng.random() * 1.3 + 0.2,
                "phase": rng.random() * math.pi * 2,
                "spd": rng.random() * 0.5 + 0.1,
            }
            for _ in range(300)
        ]

        self.nebulae = [
            {"rx": 0.12, "ry": 0.18, "r": 220, "h": 220, "a": 0.045},
            {"rx": 0.82, "ry": 0.12, "r": 190, "h": 260, "a": 0.035},
            {"rx": 0.50, "ry": 0.72, "r": 240, "h": 200, "a": 0.040},
            {"rx": 0.08, "ry": 0.82, "r": 170, "h": 280, "a": 0.030},
            {"rx": 0.88, "ry": 0.68, "r": 200, "h": 240, "a": 0.038},
            {"rx": 0.45, "ry": 0.30, "r": 160, "h": 210, "a": 0.025},
        ]

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(33)

    def _tick(self):
        self.t += 0.018
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(0, 0, W, H, QColor("#000000"))

        for n in self.nebulae:
            nx, ny = int(n["rx"] * W), int(n["ry"] * H)
            rad = QRadialGradient(nx, ny, n["r"])
            h = n["h"]
            a = n["a"]
            c0 = QColor.fromHsvF(h / 360, 0.7, 0.55, a)
            c1 = QColor.fromHsvF(h / 360, 0.6, 0.4, a * 0.35)
            c2 = QColor(0, 0, 0, 0)
            rad.setColorAt(0.0, c0)
            rad.setColorAt(0.55, c1)
            rad.setColorAt(1.0, c2)
            p.setBrush(QBrush(rad))
            p.setPen(Qt.NoPen)
            p.drawEllipse(nx - n["r"], ny - n["r"], n["r"] * 2, n["r"] * 2)

        for s in self.stars:
            tw = 0.25 + math.sin(self.t * s["spd"] + s["phase"]) * 0.75
            tw = max(0.0, min(1.0, tw))
            sx, sy = int(s["x"] * W), int(s["y"] * H)
            alpha = int(tw * 220)
            p.setBrush(QBrush(QColor(200, 225, 255, alpha)))
            p.setPen(Qt.NoPen)
            r = s["r"]
            p.drawEllipse(QPointF(sx, sy), r, r)
            if r > 0.9 and tw > 0.8:
                halo = QColor(180, 210, 255, int(tw * 18))
                p.setBrush(QBrush(halo))
                p.drawEllipse(QPointF(sx, sy), r * 3, r * 3)

        p.end()


# ─────────────────────────────────────────────
#  DUST ORB
# ─────────────────────────────────────────────
class DustOrb(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 160)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.mode = "idle"
        self.t = 0.0

        rng = random.Random(7)
        N = 500
        self.pts = []
        for _ in range(N):
            a = rng.random() * math.pi * 2
            r = rng.random() * 52
            self.pts.append({
                "a": a, "r": r,
                "x": 80 + math.cos(a) * r,
                "y": 80 + math.sin(a) * r,
                "vx": 0.0, "vy": 0.0,
                "phase": rng.random() * math.pi * 2,
                "size": rng.random() * 1.8 + 0.3,
                "trail": [],
            })

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(33)

    def set_mode(self, mode: str):
        self.mode = mode
        self.update()

    def _tick(self):
        self.t += 0.018
        self._update_particles()
        self.update()

    def _update_particles(self):
        cx, cy = 80, 80
        mode = self.mode
        t = self.t

        for i, p in enumerate(self.pts):
            if mode == "idle":
                dr = t * 0.07 + p["phase"]
                tx = cx + math.cos(p["a"] + dr) * p["r"] * (1 + math.sin(t * 0.4 + p["phase"]) * 0.05)
                ty = cy + math.sin(p["a"] + dr) * p["r"] * (1 + math.sin(t * 0.4 + p["phase"]) * 0.05)
                spd = 0.032
            elif mode == "listen":
                r2 = p["r"] * (1 + math.sin(t * 2 + p["phase"]) * 0.25)
                tx = cx + math.cos(p["a"] + t * 0.1) * r2
                ty = cy + math.sin(p["a"] + t * 0.1) * r2
                spd = 0.06
            elif mode == "speak":
                wave = math.sin(t * 1.6 + p["r"] * 0.08 + p["phase"])
                r2 = p["r"] * (0.72 + wave * 0.28)
                a2 = p["a"] + t * 0.09 + wave * 0.12
                tx = cx + math.cos(a2) * r2
                ty = cy + math.sin(a2) * r2
                spd = 0.05
            else:
                gather = math.sin(t * 1.4 + p["phase"]) * 0.5 + 0.5
                r2 = p["r"] * (0.2 + gather * 0.85)
                a2 = p["a"] - t * (0.2 + i * 0.00015)
                tx = cx + math.cos(a2) * r2
                ty = cy + math.sin(a2) * r2
                spd = 0.07

            p["vx"] += (tx - p["x"]) * spd
            p["vy"] += (ty - p["y"]) * spd
            p["vx"] *= 0.83
            p["vy"] *= 0.83
            p["x"] += p["vx"]
            p["y"] += p["vy"]

            trail = p["trail"]
            trail.append((p["x"], p["y"]))
            if len(trail) > 2:
                trail.pop(0)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = 80, 80

        p.fillRect(0, 0, 160, 160, QColor(0, 0, 0, 0))

        for pt in self.pts:
            trail = pt["trail"]
            if len(trail) >= 2:
                x0, y0 = trail[0]
                x1, y1 = trail[1]
                if self.mode == "think":
                    tc = QColor(160, 100, 255, 30)
                else:
                    tc = QColor(0, 200, 255, 28)
                pen = QPen(tc, pt["size"] * 0.5)
                p.setPen(pen)
                p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

            spd = math.hypot(pt["vx"], pt["vy"])
            dist = math.hypot(pt["x"] - cx, pt["y"] - cy) / 65
            brightness = max(0.0, 1.0 - dist * 0.3)

            if self.mode == "speak":
                alpha = int(max(18, brightness * (107 + math.sin(self.t * 1.8 + pt["phase"]) * 56)))
            else:
                alpha = int(max(18, brightness * 158))

            if self.mode == "think":
                col = QColor(160, 100, 255, alpha)
            else:
                col = QColor(0, 212, 255, alpha)

            r = pt["size"] * (1 + spd * 0.08)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(pt["x"], pt["y"]), r, r)

        p.end()


# ─────────────────────────────────────────────
#  WORKER BRIDGE
# ─────────────────────────────────────────────
class WorkerBridge:
    """Wraps the existing hud/worker.py Worker (QObject) for the HUD."""

    def __init__(self, finished_signal_callback):
        self._callback = finished_signal_callback
        self._worker = None
        self._thread = None
        if WORKER_OK:
            try:
                from PySide6.QtCore import QThread
                self._thread = QThread()
                self._worker = Worker()
                self._worker.moveToThread(self._thread)
                self._worker.finished.connect(self._callback)
                self._thread.start()
            except Exception as e:
                print(f"Worker init error: {e}")
                self._worker = None

    def process(self, text: str):
        if self._worker:
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self._worker,
                "process",
                Qt.QueuedConnection,
                Q_ARG(str, text)
            )
        else:
            self._callback("Brain not available. Check hud/worker.py.")


# ─────────────────────────────────────────────
#  PANEL WIDGET
# ─────────────────────────────────────────────
def make_label(text, size=9, color="#00d4ff44", spacing=3):
    lbl = QLabel(text)
    font = QFont("Courier New", size)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color:{color}; letter-spacing:{spacing}px; background:transparent;")
    return lbl


def make_row(key, value, val_color="#00d4ff"):
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    k = make_label(key, size=10, color="#4a8fa8", spacing=1)
    v = make_label(value, size=10, color=val_color, spacing=1)
    row.addWidget(k)
    row.addStretch()
    row.addWidget(v)
    return row, v


# ─────────────────────────────────────────────
#  MAIN HUD
# ─────────────────────────────────────────────
class JarvisHUD(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS v19")
        self.resize(1280, 720)
        self.setStyleSheet("background:#000000; color:#00d4ff; font-family:'Courier New';")

        self.worker = WorkerBridge(self._on_reply)
        self.voice = JarvisVoice() if VOICE_OK else None

        # Voice bridge — routes background thread events to Qt main thread
        if LISTENER_OK:
           print(f"[HUD] LISTENER_OK = {LISTENER_OK}")
           try:
                self._vbridge = VoiceBridge()
                self._vbridge.wake_signal.connect(self._on_wake)
                self._vbridge.command_signal.connect(self._process_voice)
                self._vbridge.idle_signal.connect(lambda: self._set_mode("idle"))

                self.listener = VoiceListener(
                    on_command=self._vbridge.command_signal.emit,
                    on_wake=self._vbridge.wake_signal.emit,
                    on_idle=self._vbridge.idle_signal.emit,
                )
                self.listener.start()
           except Exception as e:
                print(f"Voice listener error: {e}")
                self.listener = None
        else:
            self.listener = None

        self.start_time = datetime.now()
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_stats)
        self.timer.start(1000)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cosmic background
        self.bg = CosmicBackground(self)
        self.bg.setGeometry(0, 0, 1280, 720)
        self.bg.lower()

        # ── TOP BAR ──
        top = QHBoxLayout()
        top.setContentsMargins(20, 12, 20, 10)

        logo = make_label("J · A · R · V · I · S", size=16, color="#00d4ff", spacing=8)
        top.addWidget(logo)
        top.addStretch()

        for text, color in [
            ("BRAIN ONLINE", "#00ff88"),
            ("VOICE ACTIVE", "#00ff88"),
            ("OBSIDIAN PENDING", "#ffaa00"),
            ("v19", "#00d4ff"),
        ]:
            pill = make_label(text, size=8, color=color, spacing=2)
            pill.setStyleSheet(
                f"color:{color}; border:0.5px solid {color}55; "
                f"border-radius:10px; padding:3px 10px; background:{color}11;"
            )
            top.addWidget(pill)

        top_frame = QFrame()
        top_frame.setStyleSheet("border-bottom:0.5px solid #00d4ff18; background:transparent;")
        top_frame.setLayout(top)
        root.addWidget(top_frame)

        # ── MAIN GRID ──
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        # Left panel
        left = self._build_left_panel()
        mid.addWidget(left, 1)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color:#00d4ff18; background:#00d4ff18;")
        sep1.setFixedWidth(1)
        mid.addWidget(sep1)

        # Centre
        centre = self._build_centre()
        mid.addWidget(centre, 0)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#00d4ff18; background:#00d4ff18;")
        sep2.setFixedWidth(1)
        mid.addWidget(sep2)

        # Right panel
        right = self._build_right_panel()
        mid.addWidget(right, 1)

        root.addLayout(mid, 1)

        # ── BOTTOM ──
        bottom = self._build_bottom()
        root.addWidget(bottom)

    def _panel_wrap(self):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        return w, lay

    def _divider(self):
        d = QFrame()
        d.setFrameShape(QFrame.HLine)
        d.setStyleSheet("color:#00d4ff18; background:#00d4ff18; max-height:1px;")
        return d

    def _build_left_panel(self):
        w, lay = self._panel_wrap()
        lay.addWidget(make_label("MEMORY CORE", size=8, color="#00d4ff44", spacing=3))

        _, self.lbl_date = make_row("Date", "—")
        lay.addLayout(_)
        _, self.lbl_time = make_row("Time", "—")
        lay.addLayout(_)
        lay.addWidget(self._divider())

        _, self.lbl_memories = make_row("Memories stored", "12")
        lay.addLayout(_)
        _, self.lbl_lastmem = make_row("Last memory", "3m ago")
        lay.addLayout(_)
        _, self.lbl_vault = make_row("Vault", "JARVIS_CORE")
        lay.addLayout(_)
        lay.addWidget(self._divider())

        _, self.lbl_session = make_row("Session", "Active", "#00ff88")
        lay.addLayout(_)
        _, self.lbl_uptime = make_row("Uptime", "00:00:00")
        lay.addLayout(_)

        lay.addStretch()
        return w

    def _build_centre(self):
        w = QWidget()
        w.setFixedWidth(200)
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.setAlignment(Qt.AlignHCenter)

        self.orb = DustOrb()
        lay.addWidget(self.orb, alignment=Qt.AlignHCenter)

        lbl = make_label("ARC · CORE", size=8, color="#00d4ff33", spacing=3)
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        self.orb_state = make_label("Standing by", size=10, color="#00d4ff", spacing=2)
        self.orb_state.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.orb_state)

        stats = QHBoxLayout()
        cpu_lbl = make_label("CPU", size=9, color="#00d4ff44", spacing=1)
        self.cpu_val = make_label("—", size=9, color="#00ff88", spacing=1)
        ram_lbl = make_label("RAM", size=9, color="#00d4ff44", spacing=1)
        self.ram_val = make_label("—", size=9, color="#00ff88", spacing=1)
        stats.addWidget(cpu_lbl)
        stats.addWidget(self.cpu_val)
        stats.addSpacing(12)
        stats.addWidget(ram_lbl)
        stats.addWidget(self.ram_val)
        lay.addLayout(stats)
        lay.addStretch()
        return w

    def _build_right_panel(self):
        w, lay = self._panel_wrap()
        lay.addWidget(make_label("DIAGNOSTICS", size=8, color="#00d4ff44", spacing=3))

        for key, val, col in [
            ("Brain",      "● Online",    "#00ff88"),
            ("Voice",      "● Online",    "#00ff88"),
            ("Claude API", "● Connected", "#00ff88"),
            ("Obsidian",   "● Pending",   "#ffaa00"),
        ]:
            _, lv = make_row(key, val, col)
            lay.addLayout(_)

        lay.addWidget(self._divider())

        _, self.lbl_tasks = make_row("Tasks active", "0")
        lay.addLayout(_)
        _, self.lbl_nodes = make_row("Knowledge nodes", "0")
        lay.addLayout(_)
        _, self.lbl_mode = make_row("Mode", "Idle")
        lay.addLayout(_)

        lay.addStretch()
        return w

    def _build_bottom(self):
        frame = QFrame()
        frame.setStyleSheet("border-top:0.5px solid #00d4ff18; background:transparent;")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(8)

        # Small chat console
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setFixedHeight(80)
        self.chat.setStyleSheet(
            "QTextEdit {"
            "  background:rgba(0,8,20,0.65);"
            "  border:0.5px solid #00d4ff18;"
            "  border-radius:6px;"
            "  color:#3a7a96;"
            "  font-family:'Courier New';"
            "  font-size:11px;"
            "  padding:6px 10px;"
            "}"
        )
        self.chat.append('<span style="color:#00d4ff22;">// JARVIS v19 — all systems nominal</span>')
        self.chat.append('<span style="color:#00d4ff;">JARVIS: Good evening. How can I assist you?</span>')
        lay.addWidget(self.chat)

        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Enter command, sir...")
        self.inp.setStyleSheet(
            "QLineEdit {"
            "  background:rgba(0,8,20,0.75);"
            "  border:0.5px solid #00d4ff33;"
            "  border-radius:6px;"
            "  color:#00d4ff;"
            "  font-family:'Courier New';"
            "  font-size:12px;"
            "  padding:9px 14px;"
            "}"
            "QLineEdit:focus { border:0.5px solid #00d4ff66; }"
        )
        self.inp.returnPressed.connect(self._send)

        btn = QPushButton("EXECUTE")
        btn.setStyleSheet(
            "QPushButton {"
            "  background:rgba(0,20,50,0.8);"
            "  border:0.5px solid #00d4ff55;"
            "  border-radius:6px;"
            "  color:#00d4ff;"
            "  font-family:'Courier New';"
            "  font-size:10px;"
            "  letter-spacing:2px;"
            "  padding:9px 18px;"
            "}"
            "QPushButton:hover { background:rgba(0,212,255,0.12); }"
        )
        btn.clicked.connect(self._send)

        row.addWidget(self.inp)
        row.addWidget(btn)
        lay.addLayout(row)
        return frame

    # ── LOGIC ──

    def _scroll_chat(self):
        self.chat.moveCursor(QTextCursor.End)
        self.chat.ensureCursorVisible()

    def _chat_append(self, html: str):
        self.chat.append(html)
        self._scroll_chat()

    def _send(self):
        text = self.inp.text().strip()
        if not text:
            return
        self._chat_append(f'<span style="color:#00ff88;">YOU: {text}</span>')
        self.inp.clear()
        self._set_mode("think")
        self._chat_append('<span style="color:#00d4ff55;">JARVIS: Processing...</span>')
        self.worker.process(text)

    def _on_reply(self, reply: str):
        self._chat_append(f'<span style="color:#00d4ff;">JARVIS: {reply}</span>')
        self._set_mode("speak")
        if self.voice:
            def speak_then_idle():
                self.voice.speak(reply)
                self._set_mode("idle")
            threading.Thread(target=speak_then_idle, daemon=True).start()
        else:
            QTimer.singleShot(2000, lambda: self._set_mode("idle"))

    def _set_mode(self, mode: str):
        labels = {
            "idle": "Standing by",
            "listen": "Listening...",
            "speak": "Speaking...",
            "think": "Processing...",
        }
        self.orb.set_mode(mode)
        self.orb_state.setText(labels.get(mode, mode.title()))
        self.lbl_mode.setText(mode.title())

    def _on_wake(self):
        print("[HUD] _on_wake called")
        self._set_mode("listen")
        self._chat_append('<span style="color:#00ff8877;">🎤 Listening...</span>')

    def _process_voice(self, text: str):
        print(f"[HUD] _process_voice called: {text}")
        self._chat_append(f'<span style="color:#00ff88;">🎤 YOU: {text}</span>')
        self.worker.process(text)

    def _tick_stats(self):
        now = datetime.now()
        self.lbl_date.setText(now.strftime("%Y-%m-%d"))
        self.lbl_time.setText(now.strftime("%H:%M:%S"))

        elapsed = datetime.now() - self.start_time
        secs = int(elapsed.total_seconds())
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        self.lbl_uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")

        self.cpu_val.setText(str(int(psutil.cpu_percent())))
        self.ram_val.setText(str(int(psutil.virtual_memory().percent)))

    def resizeEvent(self, event):
        self.bg.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = JarvisHUD()
    window.show()
    sys.exit(app.exec())