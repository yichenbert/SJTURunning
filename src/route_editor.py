"""Native Qt map editor. Only visible OSM tiles are fetched, with HTTP disk caching."""
import json
import math
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal, QTimer, QPoint, QEvent, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QShortcut, QKeySequence
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QComboBox, QLineEdit, QMessageBox, QFileDialog)
from src.config import get_config_path
from src.dialogs import show_message
from src.map_settings import MapSettingsDialog, load_map_settings, save_map_settings
from src.route_library import RouteLibrary
from src.route_library_dialog import RouteLibraryDialog
from src.route import normalize_route, route_distance, validate_route, MAX_ROUTE_POINTS
from utils.auxiliary_util import SportsUploaderError

TILE_SIZE = 256
DEFAULT_CENTER = {'latitude': 31.0285, 'longitude': 121.4445}


def project(latitude, longitude, zoom):
    size = TILE_SIZE * 2 ** zoom
    lat = math.radians(max(-85, min(85, latitude)))
    return QPointF((longitude + 180) / 360 * size,
                   (1 - math.asinh(math.tan(lat)) / math.pi) / 2 * size)


def unproject(point, zoom):
    size = TILE_SIZE * 2 ** zoom
    return {'latitude': max(-85, min(85, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * max(0, min(size, point.y())) / size)))))),
            'longitude': max(-180, min(180, point.x() / size * 360 - 180))}


class RouteMap(QWidget):
    route_changed = Signal()
    map_status = Signal(str)

    def __init__(self, points=None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 380)
        self.setMouseTracking(True)
        self.setAccessibleName('路线地图：点击连线、手绘或平移')
        self.zoom = 16
        self.center = project(DEFAULT_CENTER['latitude'], DEFAULT_CENTER['longitude'], self.zoom)
        self.points = normalize_route(points or [])
        self.mode = 'click'
        self.history = []
        self._pressed = False
        self._pan = False
        self._last_pos = None
        self._press_pos = None
        self._edit_index = None
        self._stroke_start = None
        self._tiles = OrderedDict()
        self._pending = {}
        self._failed = set()
        self._loaded_count = 0
        self._route_revision = 0
        self._cache_key = None
        self._world_points = []
        self._world_path = QPainterPath()
        self._shutdown = False
        self._last_map_status = None
        self._wheel_accumulator = 0
        self._pinch_accumulator = 0.0
        self._trackpad_active = False
        self._gesture_timer = QTimer(self)
        self._gesture_timer.setSingleShot(True)
        self._gesture_timer.setInterval(120)
        self._gesture_timer.timeout.connect(self._end_trackpad_gesture)
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.setInterval(16)
        self._frame_timer.timeout.connect(self.update)
        self._tile_timer = QTimer(self)
        self._tile_timer.setSingleShot(True)
        self._tile_timer.setInterval(65)
        self._tile_timer.timeout.connect(self._refresh_tiles)
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(80)
        self._stats_timer.timeout.connect(self.route_changed.emit)
        self.network = QNetworkAccessManager(self)
        cache = QNetworkDiskCache(self)
        cache.setCacheDirectory(str(Path(get_config_path()).parent / 'map-cache'))
        cache.setMaximumCacheSize(100 * 1024 * 1024)
        self.network.setCache(cache)
        self.set_mode('click')
        if self.points:
            self.fit_route()

    def _origin(self):
        return self.center - QPointF(self.width() / 2, self.height() / 2)

    def screen_point(self, point):
        return project(point['latitude'], point['longitude'], self.zoom) - self._origin()

    def coordinate_at(self, position):
        return unproject(position + self._origin(), self.zoom)

    def _remember(self):
        self.history.append([dict(p) for p in self.points])
        self.history = self.history[-50:]

    def _request_frame(self):
        if not self._frame_timer.isActive():
            self._frame_timer.start()

    def _view_changed(self):
        self._request_frame()
        # Debounce loading until a gesture settles. Panning uses decoded memory tiles.
        self._tile_timer.start()

    def _changed(self, immediate=True):
        self._route_revision += 1
        self._cache_key = None
        if immediate:
            self._stats_timer.stop()
            self.route_changed.emit()
        elif not self._stats_timer.isActive():
            self._stats_timer.start()
        self._request_frame()

    def _sync_route_cache(self):
        key = (self.zoom, self._route_revision)
        if self._cache_key == key:
            return
        self._world_points = [project(p['latitude'], p['longitude'], self.zoom) for p in self.points]
        self._world_path = QPainterPath()
        if self._world_points:
            self._world_path.moveTo(self._world_points[0])
            for point in self._world_points[1:]:
                self._world_path.lineTo(point)
        self._cache_key = key

    def _visible_tiles(self):
        origin, limit = self._origin(), 2 ** self.zoom
        keys = []
        for tx in range(math.floor(origin.x() / TILE_SIZE), math.floor((origin.x() + self.width()) / TILE_SIZE) + 1):
            for ty in range(math.floor(origin.y() / TILE_SIZE), math.floor((origin.y() + self.height()) / TILE_SIZE) + 1):
                if 0 <= tx < limit and 0 <= ty < limit:
                    keys.append((self.zoom, tx, ty))
        # Load the center of the visible viewport first.
        keys.sort(key=lambda k: (k[1] * TILE_SIZE + 128 - self.center.x()) ** 2 +
                               (k[2] * TILE_SIZE + 128 - self.center.y()) ** 2)
        return keys

    def _refresh_tiles(self):
        if self._shutdown or not self.isVisible():
            return
        visible = set(self._visible_tiles())
        for key, reply in list(self._pending.items()):
            if key not in visible:
                self._pending.pop(key, None)
                reply.abort()
        for key in self._visible_tiles():
            if key not in self._tiles:
                self._load_tile(key)

    def _emit_status(self, text):
        if text != self._last_map_status:
            self._last_map_status = text
            self.map_status.emit(text)

    def set_mode(self, mode):
        self.mode = mode
        self.setCursor(Qt.CursorShape.OpenHandCursor if mode == 'pan' else Qt.CursorShape.CrossCursor)

    def undo(self):
        if self.history:
            self.points = self.history.pop()
            self._changed()

    def clear_route(self):
        if self.points:
            self._remember()
            self.points = []
            self._changed()

    def close_route(self):
        if len(self.points) >= 2 and self.points[-1] != self.points[0]:
            if len(self.points) >= MAX_ROUTE_POINTS:
                self.map_status.emit('路线点数已达上限，请撤销或清空后重画。')
                return
            self._remember()
            self.points.append(dict(self.points[0]))
            self._changed()

    def set_route(self, points):
        self._remember()
        self.points = normalize_route(points)
        self.fit_route()
        self._changed()

    def fit_route(self):
        if not self.points:
            return
        for zoom in range(19, 2, -1):
            pixels = [project(p['latitude'], p['longitude'], zoom) for p in self.points]
            left, right = min(p.x() for p in pixels), max(p.x() for p in pixels)
            top, bottom = min(p.y() for p in pixels), max(p.y() for p in pixels)
            if right - left < max(400, self.width() - 120) and bottom - top < max(260, self.height() - 120):
                self.zoom = zoom
                self.center = QPointF((left + right) / 2, (top + bottom) / 2)
                break
        self._view_changed()

    def campus(self):
        self.zoom = 16
        self.center = project(DEFAULT_CENTER['latitude'], DEFAULT_CENTER['longitude'], self.zoom)
        self._view_changed()

    def zoom_by(self, delta, anchor=None):
        target = max(3, min(19, self.zoom + delta))
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        before = self.coordinate_at(anchor)
        self.zoom = target
        self.center = project(before['latitude'], before['longitude'], target) - anchor + QPointF(self.width() / 2, self.height() / 2)
        self._view_changed()

    def retry_tiles(self):
        self._failed.clear()
        self.map_status.emit('正在重新加载当前地图…')
        self._tile_timer.start(0)
        self._request_frame()

    def _load_tile(self, key):
        if self._shutdown or key in self._pending or key in self._failed or len(self._pending) >= 6:
            return
        z, x, y = key
        req = QNetworkRequest(QUrl(f'https://tile.openstreetmap.org/{z}/{x}/{y}.png'))
        req.setRawHeader(b'User-Agent', b'SJTURunPlusRouteEditor/1.1.0 (+https://github.com/Gnonymous/SJTURunning)')
        req.setTransferTimeout(15000)
        req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self.network.get(req)
        self._pending[key] = reply
        reply.finished.connect(lambda: self._tile_finished(key, reply))

    def _tile_finished(self, key, reply):
        self._pending.pop(key, None)
        if self._shutdown or reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            reply.deleteLater()
            return
        pixmap = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError and pixmap.loadFromData(bytes(reply.readAll())):
            self._tiles[key] = pixmap
            self._loaded_count += 1
            while len(self._tiles) > 200:
                self._tiles.popitem(last=False)
            self._emit_status('地图已加载' if not self._failed else '部分图块暂未加载，可重试')
        else:
            self._failed.add(key)
            self._emit_status('地图加载失败，请检查网络后重试')
        reply.deleteLater()
        self._request_frame()
        if not self._pan and not self._trackpad_active:
            self._tile_timer.start(0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#edf2f3'))
        origin = self._origin()
        missing = False
        for key in self._visible_tiles():
            _, tx, ty = key
            x, y = round(tx * TILE_SIZE - origin.x()), round(ty * TILE_SIZE - origin.y())
            if key in self._tiles:
                self._tiles.move_to_end(key)
                painter.drawPixmap(QPoint(x, y), self._tiles[key])
            else:
                missing = True
                painter.setPen(QColor('#e0e8eb'))
                painter.drawRect(x, y, TILE_SIZE, TILE_SIZE)
                # Reuse a previously viewed lower zoom level while new tiles load.
                for levels in range(1, 4):
                    if key[0] - levels < 3:
                        break
                    factor = 2 ** levels
                    parent_key = (key[0] - levels, key[1] // factor, key[2] // factor)
                    if parent_key in self._tiles:
                        source = QRectF((key[1] % factor) * TILE_SIZE / factor,
                                        (key[2] % factor) * TILE_SIZE / factor,
                                        TILE_SIZE / factor, TILE_SIZE / factor)
                        painter.drawPixmap(QRectF(x, y, TILE_SIZE, TILE_SIZE), self._tiles[parent_key], source)
                        break
        # Scheduling is separate from painting; no disk/network request happens here.
        if missing and not self._tile_timer.isActive() and not self._pan and not self._shutdown:
            self._tile_timer.start()
        self._sync_route_cache()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._world_points:
            painter.save()
            painter.translate(-origin)
            painter.setPen(QPen(QColor('white'), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(self._world_path)
            painter.setPen(QPen(QColor('#087f83'), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(self._world_path)
            if not self._pan and not self._trackpad_active and self.mode == 'click':
                painter.setBrush(QColor('white'))
                painter.setPen(QPen(QColor('#087f83'), 1.5))
                stride = max(1, len(self._world_points) // 80)
                for i in range(0, len(self._world_points), stride):
                    point = self._world_points[i]
                    if self.rect().adjusted(-5, -5, 5, 5).contains((point-origin).toPoint()):
                        painter.drawEllipse(point, 3, 3)
            markers = [(self._world_points[0], '#087f83', '起'), (self._world_points[-1], '#e4a75b', '终')]
            for point, color, text in markers:
                painter.setPen(QPen(QColor('white'), 2))
                painter.setBrush(QColor(color))
                painter.drawEllipse(point, 12, 12)
                painter.setPen(QColor('white'))
                painter.drawText(QRectF(point.x()-12, point.y()-12, 24, 24), Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawRoundedRect(QRectF(self.width()-236, self.height()-30, 226, 24), 5, 5)
        painter.setPen(QColor('#566d75'))
        painter.drawText(QRectF(self.width()-234, self.height()-29, 222, 22), Qt.AlignmentFlag.AlignCenter, '© OpenStreetMap contributors')

    def showEvent(self, event):
        super().showEvent(event)
        self._tile_timer.start(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._tile_timer.start()

    def mousePressEvent(self, event):
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            return
        self._pressed = True
        self._last_pos = self._press_pos = event.position()
        self._pan = self.mode == 'pan' or event.button() != Qt.MouseButton.LeftButton
        self._edit_index = None
        if self._pan:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.mode == 'click':
            candidates = [(self.screen_point(p) - event.position()).manhattanLength() for p in self.points]
            if candidates and min(candidates) < 12:
                self._remember()
                self._edit_index = candidates.index(min(candidates))
        else:
            self._remember()
            self._stroke_start = len(self.points)
            self._append_point(event.position())

    def _append_point(self, position):
        if len(self.points) >= MAX_ROUTE_POINTS:
            self.map_status.emit('路线点数已达 5000，停止绘制。')
            return
        point = self.coordinate_at(position)
        if not self.points or (self.screen_point(self.points[-1]) - position).manhattanLength() >= 4:
            self.points.append(point)
            self._changed(immediate=False)

    def mouseMoveEvent(self, event):
        if not self._pressed:
            return
        position = event.position()
        if self._pan:
            self.center -= position - self._last_pos
            self._view_changed()
        elif self._edit_index is not None:
            self.points[self._edit_index] = self.coordinate_at(position)
            self._changed(immediate=False)
        elif self.mode == 'freehand':
            self._append_point(position)
        self._last_pos = position

    def mouseReleaseEvent(self, event):
        if not self._pressed:
            return
        if not self._pan and self.mode == 'click' and self._edit_index is None:
            if (event.position() - self._press_pos).manhattanLength() < 8:
                self._remember()
                self._append_point(event.position())
        elif not self._pan and self.mode == 'freehand':
            self._append_point(event.position())
        self._pressed = False
        self._edit_index = None
        was_pan = self._pan
        self._pan = False
        self._stats_timer.stop()
        if not was_pan:
            self.route_changed.emit()
        self._tile_timer.start(0)
        self.update()
        self.set_mode(self.mode)

    def _end_trackpad_gesture(self):
        self._trackpad_active = False
        self._tile_timer.start(0)
        self._request_frame()

    def wheelEvent(self, event):
        pixels = event.pixelDelta()
        if not pixels.isNull() and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # A macOS trackpad reports pixel scrolling: use it as map panning,
            # rather than jumping a whole zoom level on every scroll event.
            self.center -= QPointF(pixels)
            self._trackpad_active = True
            self._gesture_timer.start()
            self._view_changed()
        elif event.angleDelta().y():
            self._wheel_accumulator += event.angleDelta().y()
            steps = max(-1, min(1, int(self._wheel_accumulator / 120)))
            if steps:
                self._wheel_accumulator = 0
                self.zoom_by(steps, event.position())
        elif event.angleDelta().x():
            self.center -= QPointF(event.angleDelta().x() / 2, 0)
            self._view_changed()
        event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self._pinch_accumulator += event.value()
                if abs(self._pinch_accumulator) >= 0.18:
                    self.zoom_by(1 if self._pinch_accumulator > 0 else -1, event.position())
                    self._pinch_accumulator = 0.0
                event.accept()
                return True
        return super().event(event)

    def shutdown(self):
        self._shutdown = True
        self._tile_timer.stop()
        self._frame_timer.stop()
        self._stats_timer.stop()
        self._gesture_timer.stop()
        for reply in list(self._pending.values()):
            reply.abort()


class RouteEditorDialog(QDialog):
    def __init__(self, points=None, name='', parent=None):
        super().__init__(parent)
        from src.design import STYLE, card, label
        self.setObjectName('routeEditor')
        self.setWindowTitle('路线画布 · SJTURunPlus')
        self.resize(1240, 830)
        self.setMinimumSize(980, 670)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        headings = QVBoxLayout()
        headings.setSpacing(5)
        headings.addWidget(label('路线画布', 'pageTitle'))
        headings.addWidget(label('沿着地图道路，画出属于你的路线。', 'muted'))
        header.addLayout(headings)
        header.addStretch()
        self.provider_box = QComboBox()
        self.provider_box.setAccessibleName('切换地图来源')
        self.provider_box.addItem('免费地图 · OpenStreetMap', 'osm')
        self.provider_box.addItem('高德地图', 'amap')
        self.provider_box.setMinimumWidth(210)
        header.addWidget(self.provider_box)
        self.provider_badge = label('正在加载', 'badge')
        header.addWidget(self.provider_badge)
        self._button(header, '高德密钥设置', self.configure_map)
        layout.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(18)
        panel, tools = card('绘制路线')
        panel.setFixedWidth(270)
        tools.addWidget(label('路线名称', 'muted'))
        self.name_input = QLineEdit(name or '我的路线')
        self.name_input.setPlaceholderText('为这条路线命名')
        self.name_input.setMaxLength(80)
        tools.addWidget(self.name_input)
        library_actions = QHBoxLayout()
        self._button(library_actions, '我的路线', self.open_library)
        self._button(library_actions, '保存到路线库', self.save_to_library)
        tools.addLayout(library_actions)
        tools.addWidget(label('绘制方式', 'muted'))
        self.mode_box = QComboBox()
        self.mode_box.addItems(['点击连线', '手绘路线', '平移地图'])
        tools.addWidget(self.mode_box)
        self.mode_hint = label('沿道路逐点点击，拖动节点调整转弯。', 'muted', True)
        tools.addWidget(self.mode_hint)
        tools.addSpacing(8)
        tools.addWidget(label('路线长度', 'eyebrow'))
        self.stats = label('0.000 公里', 'metric')
        self.stats.setStyleSheet('font-size: 31px; color: #087f83; font-weight: 600;')
        tools.addWidget(self.stats)
        self.route_details = label('尚未添加节点', 'muted', True)
        tools.addWidget(self.route_details)
        tools.addSpacing(8)
        editing = QHBoxLayout()
        self.undo_button = self._button(editing, '撤销', lambda: self.map.undo())
        self._button(editing, '清空', lambda: self.map.clear_route())
        tools.addLayout(editing)
        close_button = QPushButton('连接起点与终点')
        close_button.clicked.connect(lambda: self.map.close_route())
        tools.addWidget(close_button)
        tools.addStretch()
        files = QHBoxLayout()
        self._button(files, '导入', self.import_route)
        self._button(files, '导出', self.export_route)
        tools.addLayout(files)
        tools.addWidget(label('路线按绘制顺序连接。\n手绘线不会自动吸附道路。', 'muted', True))
        body.addWidget(panel)
        map_panel, map_layout = card(name='mapPanel')
        map_layout.setContentsMargins(12, 12, 12, 12)
        map_layout.setSpacing(10)
        map_bar = QHBoxLayout()
        self._button(map_bar, '交大闵行', lambda: self.map.campus())
        self._button(map_bar, '查看整条路线', lambda: self.map.fit_route())
        map_bar.addStretch()
        self._button(map_bar, '−', lambda: self.map.zoom_by(-1)).setFixedWidth(42)
        self._button(map_bar, '＋', lambda: self.map.zoom_by(1)).setFixedWidth(42)
        map_layout.addLayout(map_bar)
        self.map_layout = map_layout
        self.map = self.create_map(points)
        map_layout.addWidget(self.map, 1)
        map_layout.addWidget(label('双指滑动平移  ·  捏合 / 滚轮缩放  ·  撤销 ⌘Z', 'muted'))
        body.addWidget(map_panel, 1)
        layout.addLayout(body, 1)
        footer = QHBoxLayout()
        self.status = label('正在加载地图…', 'muted')
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self._button(footer, '重试地图', lambda: self.map.retry_tiles())
        self._button(footer, '取消', self.reject)
        self.save_button = self._button(footer, '保存并使用', self.save_route)
        self.save_button.setObjectName('saveRoute')
        self.save_button.setMinimumWidth(135)
        layout.addLayout(footer)
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.map.map_status.connect(self._map_status_changed)
        self.map.route_changed.connect(self.refresh_stats)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=lambda: self.map.undo())
        self.finished.connect(lambda: self.map.shutdown())
        self.provider_box.currentIndexChanged.connect(self.change_provider)
        self.refresh_stats()

    def create_map(self, points, settings=None):
        settings = load_map_settings() if settings is None else settings
        provider = settings.get('provider', 'osm')
        if provider == 'amap' and settings.get('key') and settings.get('security_code'):
            from src.amap_view import AMapView
            widget = AMapView(points, self, settings)
        else:
            provider = 'osm'
            widget = RouteMap(points, self)
        self.active_provider = provider
        self._sync_provider_box()
        self.provider_badge.setText('高德 · 加载中' if provider == 'amap' else '免费地图 · 加载中')
        return widget

    def _sync_provider_box(self):
        with QSignalBlocker(self.provider_box):
            self.provider_box.setCurrentIndex(1 if self.active_provider == 'amap' else 0)

    def _map_status_changed(self, text):
        self.status.setText(text)
        name = '高德' if self.active_provider == 'amap' else '免费地图'
        if '已加载' in text:
            self.provider_badge.setText(name + ' · 已启用')
        elif any(word in text for word in ('失败', '未能', '暂未')):
            self.provider_badge.setText(name + ' · 加载异常')
        elif any(word in text for word in ('加载', '连接')):
            self.provider_badge.setText(name + ' · 加载中')

    def change_provider(self, index):
        target = self.provider_box.itemData(index)
        if target == self.active_provider:
            return
        settings = load_map_settings()
        if target == 'amap' and not (settings.get('key') and settings.get('security_code')):
            dialog = MapSettingsDialog(self)
            dialog.provider.setCurrentIndex(1)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._sync_provider_box()
                self.status.setText('仍在使用免费地图：高德需要 Key 和安全密钥。')
                return
            settings = load_map_settings()
        else:
            settings['provider'] = target
        self._replace_map(settings)

    def configure_map(self):
        dialog = MapSettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._replace_map(load_map_settings())

    def _replace_map(self, settings):
        self._capture_route(lambda: self._replace_map_ready(settings))

    def _capture_route(self, action):
        if getattr(self, '_capture_pending', False):
            return
        if not hasattr(self.map, 'flush_route'):
            action()
            return
        self._capture_pending = True
        self.save_button.setEnabled(False)
        self.provider_box.setEnabled(False)
        def received(success):
            self._capture_pending = False
            if self.map._shutdown:
                return
            self.provider_box.setEnabled(True)
            self.refresh_stats()
            if success:
                action()
            else:
                show_message(self, '路线尚未保存', '未能读取最新绘制的路线，请重试。')
        self.map.flush_route(received)

    def _replace_map_ready(self, settings):
        old = self.map
        points = [dict(p) for p in old.points]
        old_provider = self.active_provider
        replacement = None
        try:
            replacement = self.create_map(points, settings)
            save_map_settings(settings)
        except (OSError, RuntimeError, ImportError) as e:
            if replacement:
                replacement.shutdown();replacement.deleteLater()
            self.active_provider = old_provider
            self._sync_provider_box()
            self.provider_badge.setText(('高德' if old_provider == 'amap' else '免费地图') + ' · 保持原地图')
            show_message(self, '未能切换地图', str(e))
            return
        old.shutdown()
        self.map = replacement
        self.map.history = old.history
        self.map_layout.replaceWidget(old, self.map)
        old.hide();old.deleteLater()
        self.map.map_status.connect(self._map_status_changed)
        self.map.route_changed.connect(self.refresh_stats)
        self.status.setText('正在加载所选地图…')
        self._mode_changed(self.mode_box.currentIndex())
        self.refresh_stats()

    def open_library(self):
        dialog = RouteLibraryDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            route = dialog.selected_route
            self.map.set_route(route['points'])
            self.name_input.setText(route['name'])
            self.status.setText('已载入路线：' + route['name'])

    def save_to_library(self):
        self._capture_route(self._save_to_library_ready)

    def _save_to_library_ready(self):
        try:
            record = RouteLibrary().save(self.name_input.text(), self.map.points)
            self.name_input.setText(record['name'])
            self.status.setText('已保存到“我的路线”：' + record['name'])
            return record
        except (OSError, SportsUploaderError) as e:
            show_message(self, '路线未保存', str(e))
            return None

    def _mode_changed(self, index):
        self.map.set_mode(['click', 'freehand', 'pan'][index])
        self.mode_hint.setText(['沿道路逐点点击，拖动节点调整转弯。',
                               '按住左键沿道路画线，松开结束这一笔。',
                               '拖动浏览地图，选择你想跑的区域。'][index])
        self.map.update()

    @staticmethod
    def _button(layout, text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def refresh_stats(self):
        distance = route_distance(self.map.points)
        self.stats.setText(f'{distance / 1000:.3f} 公里')
        self.route_details.setText(f'{len(self.map.points)} 个节点 · 约 {distance / 1000 * 5:.1f} 分钟\n按 5 分钟 / 公里估算')
        self.save_button.setEnabled(len(self.map.points) >= 2 and 5 <= distance <= 100000)
        self.undo_button.setEnabled(bool(self.map.history))

    def save_route(self):
        self._capture_route(self._save_route_ready)

    def _save_route_ready(self):
        try:
            self.selected_points, _ = validate_route(self.map.points)
            self.selected_name = self.name_input.text().strip() or '我的路线'
        except SportsUploaderError as e:
            show_message(self, '路线未完成', str(e))
            return
        record = self._save_to_library_ready()
        if record is None:
            return
        self.selected_name = record['name']
        self.accept()

    def import_route(self):
        filename, _ = QFileDialog.getOpenFileName(self, '导入路线', '', '路线文件 (*.json)')
        if not filename:
            return
        try:
            if Path(filename).stat().st_size > 2 * 1024 * 1024:
                raise ValueError('路线文件过大。')
            data = json.loads(Path(filename).read_text(encoding='utf-8'))
            points, _ = validate_route(data['points'])
            if data.get('coordinate_system', 'WGS84') != 'WGS84':
                raise ValueError('仅支持 WGS84 坐标路线。')
            self.map.set_route(points)
            self.name_input.setText(str(data.get('name', '导入路线'))[:80])
        except (OSError, ValueError, KeyError, TypeError, SportsUploaderError) as e:
            show_message(self, '导入失败', str(e))

    def export_route(self):
        try:
            points, _ = validate_route(self.map.points)
        except SportsUploaderError as e:
            show_message(self, '无法导出', str(e))
            return
        filename, _ = QFileDialog.getSaveFileName(self, '导出路线', '跑步路线.json', '路线文件 (*.json)')
        if filename:
            try:
                Path(filename).write_text(json.dumps({'name': self.name_input.text().strip(),
                    'coordinate_system': 'WGS84', 'points': points}, ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError as e:
                show_message(self, '导出失败', str(e))
