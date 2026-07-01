from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class SidebarButton(QPushButton):

    def __init__(self, icon, text):

        super().__init__()

        self.icon = icon
        self.text_value = text

        self.expanded = True

        self.setCursor(Qt.PointingHandCursor)

        self.setMinimumHeight(42)

        self.setText(f"{icon}   {text}")

        self.setObjectName("sidebarButton")

    def collapse(self):

        self.expanded = False

        self.setText(self.icon)

    def expand(self):

        self.expanded = True

        self.setText(f"{self.icon}   {self.text_value}")