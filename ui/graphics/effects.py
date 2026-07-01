from dataclasses import dataclass

from PySide6.QtCore import QPoint


@dataclass
class RenderContext:

    painter: object

    center: QPoint

    animation: object