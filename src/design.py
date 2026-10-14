"""Shared visual language for the desktop workspace and route editor."""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

STYLE = '''
QWidget { font-family: "PingFang SC", "Helvetica Neue", sans-serif; font-size: 13px; color: #202c3d; }
QWidget#workspace, QDialog { background: #f4f6f9; }
QFrame#sidebar { background: #152a36; border: none; }
QFrame#sidebar QLabel { color: #97b0bb; background: transparent; }
QFrame#sidebar QLabel#brand { color: white; font-size: 19px; font-weight: 700; letter-spacing: 0px; }
QFrame#sidebar QLabel#sidebarTitle { color: #eff6f8; font-size: 14px; font-weight: 600; }
QFrame#sidebar QPushButton { text-align: left; color: #b6cbd4; border: none; background: transparent; padding: 13px 16px; border-radius: 9px; }
QFrame#sidebar QPushButton:hover { background: #203e4c; color: white; }
QFrame#sidebar QPushButton:checked { background: #2b5260; color: #ffffff; font-weight: 600; }
QFrame#card, QFrame#footer, QFrame#mapPanel { background: white; border: 1px solid #e2e8ee; border-radius: 14px; }
QFrame#heroCard { background: #ffffff; border: 1px solid #dde8e9; border-radius: 16px; }
QLabel { background: transparent; border: none; }
QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #172f3b; }
QLabel#summaryValue { font-size: 15px; color: #24394a; font-weight: 500; }
QComboBox QAbstractItemView { background: white; color: #24394a; selection-background-color: #e5f2f0; selection-color: #087f83; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; color: #24394a; }
QLabel#muted { color: #7c8a98; font-size: 12px; }
QLabel#eyebrow { color: #758c97; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#metric { color: #087f83; font-size: 38px; font-weight: 600; }
QLabel#routeTitle { color: #203b48; font-size: 21px; font-weight: 600; }
QLabel#badge { color: #147b74; background: #e6f3ef; padding: 7px 13px; border-radius: 13px; font-size: 12px; }
QPushButton { background: #ffffff; color: #33485b; border: 1px solid #dce3e9; border-radius: 8px; padding: 9px 15px; min-height: 17px; }
QPushButton:hover { border-color: #80acae; background: #f1f8f7; }
QPushButton:pressed { background: #e4f0ef; }
QPushButton:checked { background: #e5f2f0; color: #087f83; border-color: #9ccac6; }
QPushButton#primary, QPushButton#startButton, QPushButton#saveRoute { background: #087f83; border: 1px solid #087f83; color: white; font-weight: 600; padding: 10px 19px; }
QPushButton#primary:hover, QPushButton#startButton:hover, QPushButton#saveRoute:hover { background: #096d70; border-color: #096d70; }
QPushButton#stopButton { color: #b64d4d; }
QPushButton:disabled { background: #f0f3f5; border-color: #e6eaf0; color: #a2acb5; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #f8fafc; border: 1px solid #dde4eb; border-radius: 7px; padding: 8px 10px; min-height: 19px; color: #233e4c; selection-background-color: #087f83; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #087f83; background: white; }
QComboBox::drop-down { border: none; width: 26px; }
QCheckBox, QRadioButton { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; border: 1px solid #c1ced8; background: white; }
QCheckBox::indicator:checked { background: #087f83; border-color: #087f83; }
QRadioButton::indicator { width: 15px; height: 15px; border-radius: 8px; border: 1px solid #c1ced8; background: white; }
QRadioButton::indicator:checked { background: #087f83; border: 3px solid #d7eeeb; }
QScrollArea { border: none; background: transparent; }
QWidget#scrollContent { background: transparent; }
QScrollBar:vertical { border: none; background: transparent; width: 8px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #ced9e1; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTextEdit { background: #f8fafc; color: #34495d; border: 1px solid #e4eaf0; border-radius: 9px; padding: 12px; font-family: "Menlo", monospace; font-size: 12px; }
QProgressBar { border: none; background: #e9eef2; border-radius: 3px; height: 6px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #087f83; border-radius: 3px; }
QToolTip { background: #203b48; color: white; border: none; padding: 7px; }
'''


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
        painter.setBrush(QColor('#f1f7f6'))
        painter.drawRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setPen(QPen(QColor('#e2eeeb'), 1))
        for x in range(20, self.width(), 38):
            painter.drawLine(x, 0, x, self.height())
        for y in range(20, self.height(), 38):
            painter.drawLine(0, y, self.width(), y)
        points = self._points
        if len(points) < 2:
            painter.setPen(QColor('#7b9695'))
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
        painter.setPen(QPen(QColor('#087f83'), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        for point, color in ((pixels[0], '#087f83'), (pixels[-1], '#e4a75b')):
            painter.setPen(QPen(QColor('white'), 3))
            painter.setBrush(QColor(color)); painter.drawEllipse(point, 7, 7)
        painter.setPen(QColor('#7b9695'))
        painter.drawText(QRectF(12, self.height()-24, self.width()-24, 20), Qt.AlignmentFlag.AlignRight, '路线轮廓')
