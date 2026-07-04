"""
camera_panel.py — the "mini tab": a floating live view of what JARVIS
sees through the webcam. Opens automatically whenever he uses his
eyes, or on command ("show camera"); closes with "close mini tab".

While open it also writes each second's frame to memory/last_camera.jpg,
so if JARVIS wants to LOOK while the panel holds the camera, his
camera.py falls back to that fresh frame instead of fighting over the
device.
"""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
try:
    import config
    LAST_FRAME = str(config.MEMORY_DIR / "last_camera.jpg")
    CAM_INDEX = getattr(config, "CAMERA_INDEX", 0)
except Exception:
    LAST_FRAME, CAM_INDEX = "", 0

try:
    import cv2
    CV2_OK = True
except Exception:
    CV2_OK = False


class CameraPanel(QFrame):

    W, H = 340, 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self.setStyleSheet(
            "QFrame{background:rgba(8,17,28,0.94);border:1px solid #22d3ee55;"
            "border-radius:12px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        title = QLabel("◉ JARVIS VISION — LIVE")
        title.setStyleSheet("color:#22d3ee;font-size:10px;font-weight:700;"
                            "letter-spacing:2px;border:none;background:transparent;")
        top.addWidget(title)
        top.addStretch()
        x = QPushButton("✕")
        x.setFixedSize(20, 20)
        x.setCursor(Qt.PointingHandCursor)
        x.setStyleSheet(
            "QPushButton{background:#0d1e2e;border:1px solid #12324a;"
            "border-radius:5px;color:#5a8bb0;font-size:10px;}"
            "QPushButton:hover{border:1px solid #ff5566;color:#ff5566;}")
        x.clicked.connect(self.close_panel)
        top.addWidget(x)
        lay.addLayout(top)

        self.view = QLabel("starting camera…")
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("color:#5a8bb0;font-size:11px;border:none;"
                                "background:#04080f;border-radius:8px;")
        lay.addWidget(self.view, 1)

        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._save_counter = 0
        self._drag_offset = None
        self.user_moved = False      # once dragged, we stop auto-placing it
        self.setCursor(Qt.OpenHandCursor)
        self.hide()

    # ── draggable anywhere ──────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            new_pos = self.mapToParent(
                event.position().toPoint() - self._drag_offset)
            parent = self.parentWidget()
            if parent:
                x = max(0, min(new_pos.x(), parent.width() - self.width()))
                y = max(0, min(new_pos.y(), parent.height() - self.height()))
                self.move(x, y)
                self.user_moved = True

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self.setCursor(Qt.OpenHandCursor)

    # ── lifecycle ───────────────────────────────
    def open_panel(self):
        if not CV2_OK:
            self.view.setText("opencv-python not installed —\n"
                              "run the installer again")
            self.show(); self.raise_()
            return
        if self.cap is None:
            self.cap = cv2.VideoCapture(CAM_INDEX)
        self.show()
        self.raise_()
        self.timer.start(100)   # ~10 fps

    def close_panel(self):
        self.timer.stop()
        if self.cap is not None:
            try: self.cap.release()
            except Exception: pass
            self.cap = None
        self.hide()

    # ── frames ──────────────────────────────────
    def _tick(self):
        if self.cap is None or not self.cap.isOpened():
            self.view.setText("camera unavailable —\ncheck privacy settings")
            return
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.view.width(), self.view.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view.setPixmap(pix)
        # share a fresh frame with camera.py once a second
        self._save_counter += 1
        if LAST_FRAME and self._save_counter >= 10:
            self._save_counter = 0
            try:
                cv2.imwrite(LAST_FRAME, frame)
            except Exception:
                pass
