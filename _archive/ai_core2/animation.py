from PySide6.QtCore import QObject, QTimer


class AnimationEngine(QObject):

    def __init__(self, widget):

        super().__init__()

        self.widget = widget

        # -----------------------------
        # Global Rotation
        # -----------------------------

        self.outer_angle = 0.0
        self.middle_angle = 0.0
        self.inner_angle = 0.0

        # -----------------------------
        # Time Values
        # -----------------------------

        self.glow = 0.0
        self.wave = 0.0
        self.pulse = 0.0

        # -----------------------------
        # Animation Speed
        # -----------------------------

        self.speed = 1.0
        self.target_speed = 1.0

        # -----------------------------
        # Timer
        # -----------------------------

        self.timer = QTimer()

        self.timer.timeout.connect(self.update)

        self.timer.start(16)

    # --------------------------------------------------

    def set_speed(self, speed):

        self.target_speed = speed

    # --------------------------------------------------

    def update(self):

        # Smooth acceleration

        self.speed += (self.target_speed - self.speed) * 0.08

        self.outer_angle += self.speed

        self.middle_angle -= self.speed * 0.55

        self.inner_angle += self.speed * 0.25

        self.glow += 0.045 * self.speed

        self.wave += 0.020 * self.speed

        self.pulse += 0.030 * self.speed

        self.widget.update()