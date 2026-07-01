from ui.graphics.layer import Layer


class RingLayer(Layer):

    def __init__(self, rings):

        super().__init__()

        self.rings = rings

    def draw(self, painter, context):

        self.rings.draw(
            painter,
            context.center,
            context.animation,
        )


class OrbLayer(Layer):

    def __init__(self, orb):

        super().__init__()

        self.orb = orb

    def draw(self, painter, context):

        self.orb.draw(
            painter,
            context.center,
            context.animation,
        )