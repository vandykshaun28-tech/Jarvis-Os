from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
)

from PySide6.QtCore import Qt

from ui.components.sidebar_button import SidebarButton


class Sidebar(QWidget):

    def __init__(self):

        super().__init__()

        self.expanded = True

        self.buttons = []

        self.setFixedWidth(240)

        self.build_ui()

    def build_ui(self):

        root = QVBoxLayout()

        root.setContentsMargins(10,10,10,10)

        root.setSpacing(10)

        self.setLayout(root)

        # ------------------------------------------------

        self.toggle = QPushButton("☰   JARVIS")

        self.toggle.clicked.connect(
            self.toggle_sidebar
        )

        root.addWidget(self.toggle)

        # ------------------------------------------------

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(QFrame.NoFrame)

        root.addWidget(scroll)

        container = QWidget()

        scroll.setWidget(container)

        layout = QVBoxLayout()

        container.setLayout(layout)

        pages = [

            ("🏠","Dashboard"),

            ("🤖","AI Agents"),

            ("🔬","Research"),

            ("🌐","Internet"),

            ("📈","Trading"),

            ("⚙","PLC"),

            ("🚗","Vehicle"),

            ("🛒","Shopify"),

            ("🧠","Memory"),

            ("📁","Files"),

            ("📅","Calendar"),

            ("⚙","Settings"),

        ]

        for icon,name in pages:

            button = SidebarButton(icon,name)

            self.buttons.append(button)

            layout.addWidget(button)

        layout.addStretch()

        # ------------------------------------------------

        line = QFrame()

        line.setFrameShape(QFrame.HLine)

        root.addWidget(line)

        root.addWidget(QLabel("SYSTEM"))

        root.addWidget(QLabel("🟢 Claude"))

        root.addWidget(QLabel("🟢 Internet"))

        root.addWidget(QLabel("🟢 Voice"))

        self.setStyleSheet("""

        QWidget{

            background:#071019;

            border:1px solid #10344d;

            border-radius:8px;

            color:#00d9ff;

        }

        QLabel{

            border:none;

            font-size:11px;

        }

        QPushButton{

            background:#08111b;

         border:1px solid transparent;

         padding-left:18px;

         margin-top:2px;

         margin-bottom:2px;

            border:none;

            text-align:left;

            padding-left:12px;

            color:#00d9ff;

            border-radius:6px;

            font-size:13px;

        }

         QPushButton:hover{

             background:#10344d;

             border-left:3px solid #00d9ff;

        }
        
         QScrollArea{

             border:none;

             background:transparent;

        }

         QScrollBar:vertical{

             background:transparent;

             width:6px;

             margin:0px;

        }

        QScrollBar::handle:vertical{

             background:#123b5d;

             border-radius:3px;

             min-height:30px;

        }

         QScrollBar::handle:vertical:hover{

             background:#00d9ff;

        }

         QScrollBar::add-line:vertical,
         QScrollBar::sub-line:vertical{

             height:0px;

        }

         QScrollBar::add-page:vertical,
         QScrollBar::sub-page:vertical{

            background:transparent;

        }
        """)
        
    def toggle_sidebar(self):

        if self.expanded:

            self.setFixedWidth(70)

            self.toggle.setText("☰")

            for b in self.buttons:

                b.collapse()

        else:

            self.setFixedWidth(240)

            self.toggle.setText("☰   JARVIS")

            for b in self.buttons:

                b.expand()

        self.expanded = not self.expanded