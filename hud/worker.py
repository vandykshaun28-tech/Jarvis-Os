from PySide6.QtCore import QObject, Signal, Slot

from brain.brain import JarvisBrain


class Worker(QObject):

    finished = Signal(str)

    def __init__(self):

        super().__init__()

        self.brain = JarvisBrain()


    @Slot(str)
    def process(self, text):

        try:

            reply = self.brain.process(text)

        except Exception as e:

            reply = f"System error: {e}"

        self.finished.emit(reply)