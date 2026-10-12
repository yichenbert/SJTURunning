"""Official AMap JS API 2.0 inside Qt; no undocumented tile endpoints."""
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QUrl, QTimer, QFile, QIODevice
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from src.coordinates import to_amap, from_amap
from src.route import normalize_route, MAX_ROUTE_POINTS
from utils.auxiliary_util import get_base_path, SportsUploaderError


class MapPage(QWebEnginePage):
    # Provider errors can contain credentials in URLs. Show controlled UI messages only.
    def javaScriptConsoleMessage(self, level, message, line, source):
        pass


class MapBridge(QObject):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner

    @Slot(result=str)
    def bootstrap(self):
        return json.dumps(dict(self.owner.settings, points=to_amap(self.owner.points),
                               center=to_amap([{'latitude':31.0285, 'longitude':121.4445}])[0],
                               mode=self.owner.mode))

    @Slot(str, result=bool)
    def commit(self, payload):
        if self.owner._shutdown:
            return False
        try:
            if len(payload) > 600000:
                raise ValueError('payload too large')
            raw = json.loads(payload)
            points = from_amap(raw)
            # Retain untouched vertices exactly when receiving a browser edit.
            old = {tuple(p): q for p, q in zip(to_amap(self.owner.points), self.owner.points)}
            if len(raw) == len(points):
                points = [dict(old.get(tuple(p), q)) for p, q in zip(raw, points)]
            if points != self.owner.points:
                self.owner._remember()
                self.owner.points = points
                self.owner.route_changed.emit()
            return True
        except (ValueError, TypeError, KeyError, OverflowError, SportsUploaderError):
            self.owner.map_status.emit('地图返回的路线无效，请重试。')
            self.owner._send_route()
            return False

    @Slot()
    def ready(self):
        if self.owner._shutdown:
            return
        self.owner.ready = True
        self.owner._timeout.stop()
        self.owner.map_status.emit('高德地图已加载 · 路线按坐标系转换显示')
        self.owner._send_route()
        self.owner.set_mode(self.owner.mode)

    @Slot(str)
    def status(self, state):
        messages = {'loading':'正在连接高德地图…', 'failed':'高德地图未能加载，请检查 Key、安全密钥、域名白名单和网络，然后重试。',
                    'limit':'路线最多支持 5000 个点，请撤销或重新绘制。'}
        if state in messages and not self.owner._shutdown:
            self.owner.map_status.emit(messages[state])


class AMapView(QWidget):
    route_changed = Signal()
    map_status = Signal(str)

    def __init__(self, points=None, parent=None, settings=None):
        super().__init__(parent)
        self.setMinimumSize(600, 380)
        self.points = normalize_route(points or [])
        self.settings = settings or {}
        self.history = []
        self.mode = 'click'
        self.ready = False
        self._shutdown = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView(self)
        self.web.setPage(MapPage(self.web))
        self.channel = QWebChannel(self.web.page())
        self.bridge = MapBridge(self)
        self.channel.registerObject('bridge', self.bridge)
        self.web.page().setWebChannel(self.channel)
        layout.addWidget(self.web)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(lambda: self.bridge.status('failed') if not self.ready else None)
        self.retry_tiles()

    def _js(self, script):
        if self.ready and not self._shutdown:
            self.web.page().runJavaScript(script)

    def flush_route(self, callback):
        """Read the latest browser stroke before persisting or switching views."""
        if not self.ready:
            callback(True)
            return
        def received(payload):
            if self._shutdown:
                return
            success = isinstance(payload, str) and self.bridge.commit(payload)
            callback(success)
        self.web.page().runJavaScript('window.editor.snapshot();', received)

    def _remember(self):
        self.history.append([dict(p) for p in self.points])
        self.history = self.history[-50:]

    def _send_route(self):
        self._js('window.editor.setRoute(' + json.dumps(to_amap(self.points)) + ');')

    def set_mode(self, mode):
        self.mode = mode
        self._js('window.editor.setMode(' + json.dumps(mode) + ');')

    def set_route(self, points):
        points = normalize_route(points)
        self._remember()
        self.points = points
        self._send_route()
        self.fit_route()
        self.route_changed.emit()

    def undo(self):
        if self.history:
            self.points = self.history.pop()
            self._send_route()
            self.route_changed.emit()

    def clear_route(self):
        if self.points:
            self.set_route([])

    def close_route(self):
        if len(self.points) >= 2 and self.points[-1] != self.points[0]:
            if len(self.points) >= MAX_ROUTE_POINTS:
                self.bridge.status('limit')
                return
            self.set_route(self.points + [dict(self.points[0])])

    def fit_route(self):
        self._js('window.editor.fit();')

    def campus(self):
        self._js('window.editor.campus();')

    def zoom_by(self, delta):
        self._js(f'window.editor.zoom({int(delta)});')

    def retry_tiles(self):
        if self._shutdown:
            return
        self.ready = False
        html = (Path(get_base_path()) / 'assets' / 'amap.html').read_text(encoding='utf-8')
        channel_script = QFile(':/qtwebchannel/qwebchannel.js')
        if not channel_script.open(QIODevice.OpenModeFlag.ReadOnly):
            self.map_status.emit('地图通信组件未能加载，请重新安装应用。')
            return
        source = bytes(channel_script.readAll()).decode('utf-8')
        channel_script.close()
        html = html.replace('<script src="qrc:///qtwebchannel/qwebchannel.js"></script>', '<script>' + source + '</script>')
        self.web.setHtml(html, QUrl('http://localhost/'))
        self.map_status.emit('正在连接高德地图…')
        self._timeout.start(25000)

    def shutdown(self):
        self._shutdown = True
        self._timeout.stop()
        self.web.stop()
        self.web.setHtml('<html></html>')
