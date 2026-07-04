from enum import Enum


class AIState(Enum):

    IDLE = "idle"

    THINKING = "thinking"

    RESEARCHING = "researching"

    MEMORY = "memory"

    SPEAKING = "speaking"

    ERROR = "error"


class AIStateManager:

    def __init__(self):

        self.state = AIState.IDLE

    def set(self, state):

        self.state = state

    def get(self):

        return self.state

    def is_idle(self):

        return self.state == AIState.IDLE

    def is_thinking(self):

        return self.state == AIState.THINKING

    def is_speaking(self):

        return self.state == AIState.SPEAKING

    def is_researching(self):

        return self.state == AIState.RESEARCHING

    def is_memory(self):

        return self.state == AIState.MEMORY

    def is_error(self):

        return self.state == AIState.ERROR