from math import cos, sin, radians
from random import uniform

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


class Particle:

    def __init__(self):

        self.angle = uniform(0, 360)

        self.radius = uniform(10, 90)

        self.speed = uniform(0.2, 1.5)

        self.size = uniform(2, 5)

        self.alpha = uniform(80, 220)

        self.offset = uniform(0, 360)


class ParticleEngine:

    def __init__(self):

        self.particles = [

            Particle()

            for _ in range(220)

        ]

    # ---------------------------------------------------

    def draw(

        self,

        painter,

        center,

        animation,

    ):

        painter.save()

        painter.setPen(Qt.NoPen)

        for particle in self.particles:

            angle = radians(

                particle.angle +

                animation.outer_angle *

                particle.speed

            )

            radius = particle.radius + (

                sin(

                    animation.wave +

                    particle.offset

                ) * 4

            )

            x = center.x() + cos(angle) * radius

            y = center.y() + sin(angle) * radius

            glow = QColor(

                90,

                220,

                255,

                int(particle.alpha),

            )

            painter.setBrush(glow)

            painter.drawEllipse(

                int(x - particle.size / 2),

                int(y - particle.size / 2),

                int(particle.size),

                int(particle.size),

            )

        painter.restore()