class Renderer:

    def __init__(self):

        self.layers = []

    def add(self, layer):

        self.layers.append(layer)

    def render(self, painter, context):

        for layer in self.layers:

            if layer.enabled:

                layer.draw(
                    painter,
                    context,
                )