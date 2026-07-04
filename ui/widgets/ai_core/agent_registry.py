from dataclasses import dataclass


@dataclass
class Agent:

    name: str

    angle: float

    icon: str = "\u25cf"

    radius: int = 340

    color: str = "#22d3ee"

    state: str = "idle"

    enabled: bool = True


class AgentRegistry:

    def __init__(self):

        # Angles: -90 = top, increasing clockwise (matches concept image)

        self.agents = [

            Agent("Claude",   -90, "\U0001f9e0", color="#b06bff"),

            Agent("Research", -45, "\U0001f50d", color="#22d3ee"),

            Agent("Internet",   0, "\U0001f310", color="#3b82f6"),

            Agent("Voice",      45, "\U0001f3a4", color="#14b8a6"),

            Agent("Shopify",    90, "\U0001f6d2", color="#d946ef"),

            Agent("Vehicle",   135, "\U0001f697", color="#f5a623"),

            Agent("Trading",   180, "\U0001f4c8", color="#2dd4ff"),

            Agent("Memory",    225, "\U0001f5c4", color="#22c55e"),

        ]

    def all(self):

        return self.agents

    def get(self, name):

        for agent in self.agents:

            if agent.name == name:

                return agent

        return None
