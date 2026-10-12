import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from src.coordinates import wgs84_to_gcj02, gcj02_to_wgs84, to_amap, from_amap
from src.map_settings import save_map_settings, load_map_settings, MapSettingsDialog
from src.dialogs import SummaryDialog
from src.route import route_distance


class CoordinatesTests(unittest.TestCase):
    def test_known_beijing_coordinate(self):
        lat, lon = wgs84_to_gcj02(39.908823, 116.397470)
        self.assertAlmostEqual(lat, 39.9102265, places=6)
        self.assertAlmostEqual(lon, 116.4037136, places=6)

    def test_campus_roundtrip_and_display_offset(self):
        original = [{'latitude':31.0285,'longitude':121.4445}, {'latitude':31.029,'longitude':121.445}]
        converted = to_amap(original)
        self.assertGreater(abs(converted[0][0]-original[0]['longitude']), .003)
        restored = from_amap(converted)
        for a,b in zip(original, restored):
            self.assertAlmostEqual(a['latitude'], b['latitude'], places=8)
            self.assertAlmostEqual(a['longitude'], b['longitude'], places=8)
        self.assertAlmostEqual(route_distance(original), route_distance(restored), places=3)

    def test_overseas_unchanged_and_invalid_input_rejected(self):
        self.assertEqual(wgs84_to_gcj02(51.5,-.1), (51.5,-.1))
        self.assertEqual(gcj02_to_wgs84(51.5,-.1), (51.5,-.1))
        from utils.auxiliary_util import SportsUploaderError
        for points in ([[float('nan'),31]], [[121,95]], [[121]], [[121,31]]*5001):
            with self.assertRaises((ValueError, SportsUploaderError)):
                from_amap(points)


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            widget.close();widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_confirmation_dark_system_theme_readable_and_cancel_by_escape(self):
        old = self.app.palette()
        dark = QPalette(old)
        dark.setColor(QPalette.ColorRole.Window,QColor('#303030'))
        self.app.setPalette(dark)
        try:
            dialog = SummaryDialog('确认本次提交',[('账号','<test@example.com>'),('日期','2026-10-11')])
            dialog.show();self.app.processEvents()
            self.assertEqual(dialog.palette().color(QPalette.ColorRole.Window).name(), '#f4f6f9')
            self.assertEqual(dialog.cancel_button.text(),'返回修改')
            self.assertEqual(dialog.confirm_button.text(),'确认并开始')
            QTest.keyClick(dialog,Qt.Key.Key_Escape)
            self.assertEqual(dialog.result(),QDialog.DialogCode.Rejected)
        finally:
            self.app.setPalette(old)

    def test_map_settings_persist_separately_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory, patch('src.map_settings.get_config_path',return_value=str(Path(directory)/'config.json')):
            data={'provider':'amap','key':'test-only','security_code':'test-only-code'}
            save_map_settings(data)
            self.assertEqual(load_map_settings(),data)
            # Windows chmod exposes read-only flags, not POSIX permission bits.
            if os.name == 'posix':
                self.assertEqual((Path(directory)/'map-settings.json').stat().st_mode & 0o777,0o600)
            self.assertFalse((Path(directory)/'config.json').exists())
            dialog=MapSettingsDialog()
            self.assertEqual(dialog.provider.currentData(),'amap')

    def test_missing_amap_key_cannot_enable_provider(self):
        with tempfile.TemporaryDirectory() as directory, patch('src.map_settings.get_config_path',return_value=str(Path(directory)/'config.json')),patch('src.map_settings.show_message') as message:
            dialog=MapSettingsDialog();dialog.provider.setCurrentIndex(1);dialog.save()
            message.assert_called_once()
            self.assertFalse((Path(directory)/'map-settings.json').exists())
