from PySide6.QtCore import QObject, QTimer

from ui.widgets.ai_core.state import AIState


class AnimationEngine(QObject):

    def __init__(self, widget):

        super().__init__()

        self.widget = widget

        self.state = AIState.IDLE

        # Ring rotation
        self.outer_angle = 0.0
        self.middle_angle = 0.0
        self.inner_angle = 0.0

        # Animation values used by the renderer
        self.glow = 0.0
        self.pulse = 0.0
        self.wave = 0.0

        # Speed
        self.speed = 0.25

        self.timer = QTimer()

        self.timer.timeout.connect(self.update)

        self.timer.start(16)

    # --------------------------------------------------

    def set_state(self, state):

        self.state = state

        if state == AIState.IDLE:

            self.speed = 0.25

        elif state == AIState.THINKING:

            self.speed = 1.8

        elif state == AIState.RESEARCHING:

            self.speed = 2.5

        elif state == AIState.SPEAKING:

            self.speed = 1.2

        elif state == AIState.MEMORY:

            self.speed = 0.8

        elif state == AIState.ERROR:

            self.speed = 3.0

    # --------------------------------------------------

    def update(self):

        # Ring rotation

        self.outer_angle += self.speed

        self.middle_angle -= self.speed * 0.60

        self.inner_angle += self.speed * 0.35

        # Continuous animation values

        self.glow += 0.05 * self.speed

        self.pulse += 0.03 * self.speed

        self.wave += 0.02 * self.speed

        self.widget.update()