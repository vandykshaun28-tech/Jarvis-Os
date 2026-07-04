from ui.graphics.renderer import Renderer
from ui.graphics.effects import RenderContext

from ui.widgets.ai_core.orb import Orb
from ui.widgets.ai_core.rings import Rings
from ui.widgets.ai_core.agent_nodes import AgentNodes
from ui.widgets.ai_core.connection_lines import ConnectionLines

from ui.widgets.ai_core.layers import (
    RingLayer,
    AgentNodeLayer,
    ConnectionLayer,
    OrbLayer,
)


class AICoreRenderer(Renderer):

    def __init__(self):

        super().__init__()

        self.orb = Orb()

        self.rings = Rings()

        self.nodes = AgentNodes()

        self.connections = ConnectionLines(self.nodes)

        self.add(
            RingLayer(self.rings)
        )

        self.add(
            ConnectionLayer(self.connections)
        )

        self.add(
            AgentNodeLayer(self.nodes)
        )

        self.add(
            OrbLayer(self.orb)
        )

    def draw(
        self,
        painter,
        center,
        animation,
    ):

        context = RenderContext(
            painter=painter,
            center=center,
            animation=animation,
        )

        self.render(
            painter,
            context,
        )