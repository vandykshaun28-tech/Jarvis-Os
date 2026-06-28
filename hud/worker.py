from PySide6.QtCore import QObject, Signal, Slot
import sys
import os
import importlib.util


def _load_brain():
    brain_path = os.path.join(
        os.path.dirname(__file__), '..', 'brain', 'brain.py'
    )
    brain_path = os.path.abspath(brain_path)
    spec   = importlib.util.spec_from_file_location("JarvisBrainModule", brain_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JarvisBrain()


class Worker(QObject):

    finished = Signal(str)

    def __init__(self):
        super().__init__()
        try:
            self.brain = _load_brain()
            print("[Worker] Brain loaded successfully.")
        except Exception as e:
            print(f"[Worker] Brain load error: {e}")
            import traceback
            traceback.print_exc()
            self.brain = None

    @Slot(str)
    def process(self, text: str):
        if self.brain is None:
            self.finished.emit("Brain not available. Check brain/brain.py.")
            return
        try:
            reply = self.brain.process(text)
            self.finished.emit(reply)
        except Exception as e:
            print(f"[Worker] Error: {e}")
            self.finished.emit(f"System error: {e}")