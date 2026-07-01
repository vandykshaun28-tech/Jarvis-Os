import sys

from PySide6.QtWidgets import QApplication

from ui.layouts.main_window import MainWindow

from ui.styles.theme import THEME

def main():

    app = QApplication(sys.argv)

    window = MainWindow()

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()