"""Map preferences are separate from route data and account credentials."""
import json
import os
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLineEdit, QPushButton
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from src.config import get_config_path
from src.design import STYLE, label
from src.dialogs import show_message


def load_map_settings():
    try:
        data = json.loads((Path(get_config_path()).parent / 'map-settings.json').read_text())
        if not isinstance(data, dict):
            return {}
        return {k:str(data.get(k, '')) for k in ('provider', 'key', 'security_code')}
    except (OSError, ValueError):
        return {}


def save_map_settings(data):
    path = Path(get_config_path()).parent / 'map-settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class MapSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('地图来源与设置')
        self.setStyleSheet(STYLE)
        self.resize(540, 490)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(label('地图来源', 'pageTitle'))
        layout.addWidget(label('高德地图可提供国内道路与地点标注。', 'muted', True))
        self.provider = QComboBox()
        self.provider.addItem('OpenStreetMap · 无需密钥', 'osm')
        self.provider.addItem('高德地图 · 需要密钥', 'amap')
        layout.addWidget(self.provider)
        layout.addWidget(label('高德 Web 端（JS API）Key', 'cardTitle'))
        self.key = QLineEdit()
        self.key.setPlaceholderText('填写你申请的 JS API Key')
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.key)
        layout.addWidget(label('安全密钥（securityJsCode）', 'cardTitle'))
        self.security = QLineEdit()
        self.security.setPlaceholderText('填写与 Key 配套的安全密钥')
        self.security.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.security)
        layout.addWidget(label('在高德开放平台创建 Web 端（JS API）应用；如配置域名白名单，请允许 localhost。密钥保存在本机，仅供高德地图使用。', 'muted', True))
        docs = QPushButton('打开高德密钥申请说明 ↗')
        docs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://lbs.amap.com/api/javascript-api-v2/prerequisites')))
        layout.addWidget(docs)
        layout.addWidget(label('已有路线会转换后显示，保存和导出仍使用 WGS84。切换地图不会移动或重写原路线。', 'muted', True))
        layout.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton('取消'); cancel.clicked.connect(self.reject); row.addWidget(cancel)
        save = QPushButton('保存地图设置'); save.setObjectName('primary'); save.clicked.connect(self.save); row.addWidget(save)
        layout.addLayout(row)
        data = load_map_settings()
        self.provider.setCurrentIndex(1 if data.get('provider') == 'amap' else 0)
        self.key.setText(data.get('key', ''))
        self.security.setText(data.get('security_code', ''))

    def save(self):
        data = {'provider':self.provider.currentData(), 'key':self.key.text().strip(),
                'security_code':self.security.text().strip()}
        if data['provider'] == 'amap' and not all((data['key'], data['security_code'])):
            show_message(self, '请填写高德密钥', '需要 Web 端（JS API）Key 和配套安全密钥，填写后即可启用高德地图。')
            return
        try:
            save_map_settings(data)
        except OSError:
            show_message(self, '设置未保存', '无法写入本机地图设置，请检查目录权限。')
            return
        self.accept()
