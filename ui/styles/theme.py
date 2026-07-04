from ui.styles.colors import *


THEME = f"""

QWidget{{

    background:{BACKGROUND};

    color:{ACCENT};

    font-family:Segoe UI;

}}

QFrame{{

    background:{PANEL};

    border:1px solid {BORDER};

    border-radius:10px;

}}

QLabel{{

    border:none;

}}

QPushButton{{

    background:{BUTTON};

    border:1px solid transparent;

    border-radius:8px;

    color:{ACCENT};

    padding:8px;

}}

QPushButton:hover{{

    background:{HOVER};

    border-left:3px solid {ACCENT};

}}

QScrollArea{{

    border:none;

    background:transparent;

}}

QScrollBar:vertical{{

    background:transparent;

    width:6px;

}}

QScrollBar::handle:vertical{{

    background:{BORDER};

    border-radius:3px;

}}

QScrollBar::handle:vertical:hover{{

    background:{ACCENT};

}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical{{

    height:0px;

}}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical{{

    background:transparent;

}}

"""
