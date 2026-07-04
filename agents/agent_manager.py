"""
agent_manager.py
────────────────
Owns every background agent, starts them at boot, and gives the brain
and the UI one place to ask "what's everyone doing?".
"""

import config
from agents.shopify_agent import ShopifyAgent
from agents.trading_agent import TradingAgent
from agents.mind import Mind


class AgentManager:

    def __init__(self, brain=None):
        self.brain  = brain
        self.agents = {}
        for cls in (ShopifyAgent, TradingAgent):
            a = cls(brain=brain)
            self.agents[a.name.lower()] = a
        if config.MIND_ENABLED:
            m = Mind(brain=brain)
            self.agents[m.name.lower()] = m

    # ── lifecycle ───────────────────────────────
    def start_all(self):
        for a in self.agents.values():
            a.start()
        print(f"[Agents] {len(self.agents)} agents running: "
              + ", ".join(a.name for a in self.agents.values()))

    def stop_all(self):
        for a in self.agents.values():
            a.stop()

    def get(self, name):
        return self.agents.get(str(name).lower().strip())

    def control(self, name, action):
        a = self.get(name)
        if not a:
            return (f"No agent called '{name}', sir. I have: "
                    + ", ".join(x.name for x in self.agents.values()))
        if action == "start":
            return a.start()
        if action == "stop":
            return a.stop()
        return "Action must be start or stop."

    # ── reporting ───────────────────────────────
    def snapshot(self):
        return [a.snapshot() for a in self.agents.values()]

    def status_text(self):
        lines = []
        for a in self.agents.values():
            s = a.snapshot()
            lines.append(f"{s['name']}: {s['status']}"
                         + (f" — {s['last_message'][:90]}" if s['last_message'] else ""))
        return "\n".join(lines)
