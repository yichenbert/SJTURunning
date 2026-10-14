"""Predictable, readable dialogs in both macOS appearance modes."""
from src.appearance import bind_theme
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QScrollArea, QWidget
from src.design import STYLE, card, label


class SummaryDialog(QDialog):
    def __init__(self, title, rows, parent=None, action='确认并开始'):
        super().__init__(parent)
        self.setObjectName('summaryDialog')
        self.setWindowTitle(title)
        bind_theme(self)
        self.resize(540, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(label(title, 'pageTitle'))
        layout.addWidget(label('检查以下信息，准备好后再继续。', 'muted'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName('scrollContent')
        details = QVBoxLayout(content)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(12)
        for heading, value in rows:
            frame, section = card()
            section.setContentsMargins(18, 14, 18, 14)
            section.setSpacing(6)
            section.addWidget(label(heading, 'muted'))
            text = label(str(value), 'summaryValue', True)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            section.addWidget(text)
            details.addWidget(frame)
        details.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton('返回修改')
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = QPushButton(action)
        self.confirm_button.setObjectName('primary')
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)
        self.cancel_button.setFocus()


def show_message(parent, title, message):
    dialog = SummaryDialog(title, [('提示', message)], parent, '知道了')
    dialog.cancel_button.hide()
    dialog.resize(500, 300)
    dialog.exec()
