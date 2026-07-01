from enum import Enum


class AIState(Enum):

    IDLE = 0

    THINKING = 1

    SPEAKING = 2

    WORKING = 3

    ERROR = 4