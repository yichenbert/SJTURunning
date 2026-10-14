"""Shared visual language for the desktop workspace and route editor."""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

def stylesheet(c):
    template = '''
QWidget { font-family: "PingFang SC", "Helvetica Neue", sans-serif; font-size: 13px; color: $ink; }
QWidget#workspace, QDialog { background: $bg; }
QFrame#sidebar { background: $sidebar; border: none; border-right: 1px solid $border; }
QFrame#sidebar QLabel { color: $muted; background: transparent; }
QFrame#sidebar QLabel#brand { color: $ink; font-size: 19px; font-weight: 600; }
QFrame#sidebar QLabel#sidebarTitle { font-size: 13px; }
QFrame#sidebar QPushButton { text-align: left; color: $muted; border: none; background: transparent; padding: 12px 14px; border-radius: 8px; }
QFrame#sidebar QPushButton:hover, QFrame#sidebar QPushButton:checked { background: $hover; color: $ink; }
QFrame#card, QFrame#footer, QFrame#mapPanel, QFrame#heroCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#pageTitle { font-size: 28px; font-weight: 600; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; }
QLabel#summaryValue { font-size: 15px; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#eyebrow { color: $muted; font-size: 11px; }
QLabel#metric { font-size: 34px; font-weight: 600; }
QLabel#editorMetric { font-size: 29px; font-weight: 600; }
QLabel#routeTitle { font-size: 21px; font-weight: 600; }
QLabel#badge { color: $muted; background: $subtle; padding: 7px 12px; border-radius: 8px; font-size: 12px; }
QPushButton { background: $surface; color: $ink; border: 1px solid $border; border-radius: 8px; padding: 9px 14px; min-height: 18px; }
QPushButton:hover, QPushButton:pressed { background: $hover; }
QPushButton:checked { background: $soft; color: $accent; border-color: $accent; }
QPushButton#primary, QPushButton#startButton, QPushButton#saveRoute { background: $ink; border-color: $ink; color: $bg; font-weight: 600; padding: 10px 18px; }
QPushButton#primary:hover, QPushButton#startButton:hover, QPushButton#saveRoute:hover { background: $muted; border-color: $muted; color: $bg; }
QPushButton#stopButton { color: $error; }
QPushButton:disabled { background: $subtle; border-color: $border; color: $muted; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit { background: $surface; color: $ink; border: 1px solid $border; border-radius: 7px; padding: 8px 10px; min-height: 19px; selection-background-color: $soft; selection-color: $accent; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: $surface; color: $ink; border: 1px solid $border; selection-background-color: $soft; selection-color: $accent; }
QCheckBox, QRadioButton { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; border: 1px solid $muted; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border: 3px solid $soft; }
QRadioButton::indicator { width: 15px; height: 15px; border-radius: 8px; border: 1px solid $muted; background: $surface; }
QRadioButton::indicator:checked { background: $accent; border: 3px solid $soft; }
QScrollArea { border: none; background: transparent; }
QWidget#scrollContent { background: transparent; }
QScrollBar:vertical { border: none; background: $subtle; width: 8px; margin: 3px 0; }
QScrollBar::handle:vertical { background: $border; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTextEdit, QListWidget { background: $surface; color: $ink; border: 1px solid $border; border-radius: 9px; padding: 10px; }
QTextEdit { font-family: "Menlo", monospace; font-size: 12px; }
QListWidget::item { padding: 12px; border-bottom: 1px solid $border; }
QListWidget::item:selected { background: $soft; color: $accent; }
QProgressBar { border: none; background: $subtle; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
QToolTip { background: $surface; color: $ink; border: 1px solid $border; padding: 7px; }
'''
    from string import Template
    return Template(template).substitute(c)


# Kept for callers importing the legacy constant; windows use bind_theme instead.
from src.appearance import LIGHT, appearance
STYLE = stylesheet(LIGHT)



def label(text, role=None, wrap=False):
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


def card(title=None, subtitle=None, name='card'):
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(13)
    if title:
        layout.addWidget(label(title, 'cardTitle'))
    if subtitle:
        layout.addWidget(label(subtitle, 'muted', True))
    return frame, layout


class RouteOverview(QWidget):
    """A lightweight route outline, explicitly separate from the live map."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(230, 150)
        self._points = []

    def set_points(self, points):
        from src.route_editor import project
        self._points = [project(p['latitude'], p['longitude'], 12) for p in points]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(appearance().colors['subtle']))
        painter.drawRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setPen(QPen(QColor(appearance().colors['border']), 1))
        for x in range(20, self.width(), 38):
            painter.drawLine(x, 0, x, self.height())
        for y in range(20, self.height(), 38):
            painter.drawLine(0, y, self.width(), y)
        points = self._points
        if len(points) < 2:
            painter.setPen(QColor(appearance().colors['muted']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '绘制你的第一条路线')
            return
        left, top = min(p.x() for p in points), min(p.y() for p in points)
        width = max(p.x() for p in points) - left
        height = max(p.y() for p in points) - top
        scale = min((self.width() - 55) / max(width, 1), (self.height() - 60) / max(height, 1))
        offset = QPointF((self.width() - width * scale) / 2, (self.height() - height * scale) / 2)
        pixels = [(p - QPointF(left, top)) * scale + offset for p in points]
        path = QPainterPath(pixels[0])
        for point in pixels[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor('white'), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(appearance().colors['accent']), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        for point, color in ((pixels[0], '#087f83'), (pixels[-1], '#e4a75b')):
            painter.setPen(QPen(QColor('white'), 3))
            painter.setBrush(QColor(color)); painter.drawEllipse(point, 7, 7)
        painter.setPen(QColor(appearance().colors['muted']))
        painter.drawText(QRectF(12, self.height()-24, self.width()-24, 20), Qt.AlignmentFlag.AlignRight, '路线轮廓')
