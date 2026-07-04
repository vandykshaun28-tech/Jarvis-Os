from ui.widgets.ai_core2.molecular_reactor import MolecularReactor
from ui.widgets.ai_core2.particles import ParticleEngine


class AICore2Renderer:

    def __init__(self):

        self.reactor = MolecularReactor()

        self.particles = ParticleEngine()

    def draw(
        self,
        painter,
        center,
        animation,
    ):

        # Draw particles first

        self.particles.draw(
            painter,
            center,
            animation,
        )

        # Draw reactor on top

        self.reactor.draw(
            painter,
            center,
            animation,
        )