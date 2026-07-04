from abc import ABC, abstractmethod


class Layer(ABC):

    def __init__(self, enabled=True):

        self.enabled = enabled

    @abstractmethod
    def draw(self, painter, context):
        pass