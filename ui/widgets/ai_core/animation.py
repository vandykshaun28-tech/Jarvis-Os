from PySide6.QtCore import QObject, QTimer


class AnimationEngine(QObject):

    def __init__(self, parent=None):

        super().__init__(parent)

        self.outer_angle = 0.0
        self.inner_angle = 0.0
        self.glow = 0.0

        self.timer = QTimer()

        self.timer.timeout.connect(self.tick)

        self.timer.start(16)

    def tick(self):

        self.outer_angle += 0.8
        self.inner_angle -= 1.4
        self.glow += 0.05

        if self.outer_angle >= 360:
            self.outer_angle = 0

        if self.inner_angle <= -360:
            self.inner_angle = 0

        if self.parent():
            self.parent().update()