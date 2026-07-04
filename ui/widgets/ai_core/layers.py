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


class ConnectionLayer(Layer):

    def __init__(self, connections):
        super().__init__()
        self.connections = connections

    def draw(self, painter, context):
        self.connections.draw(
            painter,
            context.center,
            context.animation,
        )


class PacketLayer(Layer):

    def __init__(self, packets):
        super().__init__()
        self.packets = packets

    def draw(self, painter, context):
        self.packets.draw(
            painter,
            context.center,
            context.animation,
        )


class AgentNodeLayer(Layer):

    def __init__(self, nodes):
        super().__init__()
        self.nodes = nodes

    def draw(self, painter, context):
        self.nodes.draw(
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