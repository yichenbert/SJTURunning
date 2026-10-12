import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QPixmap, QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog
from src.route_editor import RouteEditorDialog, RouteMap, project
from qtui import SportsUploaderUI, WorkerThread


class RouteEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.directory.name) / 'config.json'
        self.path_patch = patch('src.config.get_config_path', return_value=str(self.config_path))
        self.path_patch.start()
        self.editor_path_patch = patch('src.route_editor.get_config_path', return_value=str(self.config_path))
        self.editor_path_patch.start()
        self.tile_patch = patch.object(RouteMap, '_load_tile')
        self.tile_patch.start()

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.tile_patch.stop()
        self.editor_path_patch.stop()
        self.path_patch.stop()
        self.directory.cleanup()

    def dialog(self):
        dialog = RouteEditorDialog()
        dialog.show()
        self.app.processEvents()
        return dialog

    def test_click_undo_and_save_route(self):
        dialog = self.dialog()
        QTest.mouseClick(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(200, 160))
        QTest.mouseClick(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(350, 160))
        QTest.mouseClick(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(350, 270))
        self.assertEqual(len(dialog.map.points), 3)
        self.assertTrue(dialog.save_button.isEnabled())
        QTest.mouseClick(dialog.undo_button, Qt.MouseButton.LeftButton)
        self.assertEqual(len(dialog.map.points), 2)
        dialog.name_input.setText('测试路线')
        QTest.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.selected_name, '测试路线')
        self.assertEqual(len(dialog.selected_points), 2)

    def test_freehand_stroke_undo_as_one_action(self):
        dialog = self.dialog()
        dialog.mode_box.setCurrentIndex(1)
        QTest.mousePress(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(200, 150))
        for point in (QPoint(220, 170), QPoint(250, 180), QPoint(280, 210)):
            QTest.mouseMove(dialog.map, point)
        QTest.mouseRelease(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(300, 230))
        self.assertGreaterEqual(len(dialog.map.points), 4)
        dialog.map.undo()
        self.assertEqual(dialog.map.points, [])

    def test_pan_does_not_draw_and_zoom_anchor_stays_in_place(self):
        dialog = self.dialog()
        dialog.mode_box.setCurrentIndex(2)
        before = QPointF(dialog.map.center)
        QTest.mousePress(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(200, 150))
        QTest.mouseMove(dialog.map, QPoint(250, 170))
        QTest.mouseRelease(dialog.map, Qt.MouseButton.LeftButton, pos=QPoint(250, 170))
        self.assertEqual(dialog.map.points, [])
        self.assertNotEqual(dialog.map.center, before)
        anchor = QPoint(300, 250).toPointF()
        coordinate = dialog.map.coordinate_at(anchor)
        dialog.map.zoom_by(1, anchor)
        after = dialog.map.coordinate_at(anchor)
        self.assertAlmostEqual(coordinate['latitude'], after['latitude'], places=10)
        self.assertAlmostEqual(coordinate['longitude'], after['longitude'], places=10)

    def test_route_persists_and_restores_in_main_ui_without_credentials(self):
        ui = SportsUploaderUI()
        ui.route_points = [{'latitude': 31.028, 'longitude': 121.44},
                           {'latitude': 31.029, 'longitude': 121.442}]
        ui.route_name = '保存测试'
        ui.route_enabled.setChecked(True)
        ui._auto_save_config()
        saved = json.loads(self.config_path.read_text())
        self.assertEqual(saved['自定义路线'], ui.route_points)
        self.assertNotIn('PASSWORD', saved)
        restored = SportsUploaderUI()
        self.assertEqual(restored.route_points, ui.route_points)
        self.assertTrue(restored.route_enabled.isChecked())
        self.assertFalse(restored.dist_spin.isEnabled())
        restored.username_input.setText('offline-test')
        restored.password_input.setText('not-a-real-password')
        settings = restored.get_settings_from_ui()
        self.assertEqual(settings['APP_CONFIG']['自定义路线'], ui.route_points)
        self.assertEqual(settings['START_LATITUDE'], ui.route_points[0]['latitude'])

    def test_trackpad_pixel_scroll_pans_without_changing_zoom(self):
        dialog = self.dialog()
        before, zoom = QPointF(dialog.map.center), dialog.map.zoom
        event = QWheelEvent(QPointF(300, 200), QPointF(300, 200), QPoint(40, -20), QPoint(0, -15),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.ScrollUpdate, False)
        QApplication.sendEvent(dialog.map, event)
        self.assertEqual(dialog.map.zoom, zoom)
        self.assertEqual(dialog.map.center, before-QPointF(40, -20))
        self.assertEqual(dialog.map.points, [])

    def test_partial_mouse_wheel_events_accumulate_before_zooming(self):
        dialog = self.dialog()
        zoom = dialog.map.zoom
        for i in range(4):
            event = QWheelEvent(QPointF(300, 200), QPointF(300, 200), QPoint(), QPoint(0, 30),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(dialog.map, event)
            self.assertEqual(dialog.map.zoom, zoom + (1 if i == 3 else 0))

    def test_large_scroll_event_does_not_skip_many_zoom_levels(self):
        dialog = self.dialog()
        zoom = dialog.map.zoom
        event = QWheelEvent(QPointF(300, 200), QPointF(300, 200), QPoint(), QPoint(0, -2400),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(dialog.map, event)
        self.assertEqual(dialog.map.zoom, zoom - 1)

    def test_pan_render_reuses_projected_route_and_does_not_start_requests(self):
        dialog = self.dialog()
        dialog.map.set_route([{'latitude':31.028, 'longitude':121.44},
                              {'latitude':31.029, 'longitude':121.443}])
        image = QPixmap(dialog.map.size())
        dialog.map.render(image)
        with patch('src.route_editor.project', wraps=project) as projection, \
             patch.object(dialog.map, '_load_tile') as load:
            for i in range(6):
                dialog.map.center += QPointF(5, 3)
                dialog.map.render(image)
            projection.assert_not_called()
            load.assert_not_called()

    def test_navigation_and_missing_account_do_not_start_network(self):
        ui = SportsUploaderUI()
        ui.show()
        self.app.processEvents()
        QTest.mouseClick(ui.nav_buttons[1], Qt.MouseButton.LeftButton)
        self.assertEqual(ui.pages.currentIndex(), 1)
        ui.nav_buttons[0].setChecked(True)
        self.assertEqual(ui.pages.currentIndex(), 0)
        ui.start_upload()
        self.assertEqual(ui.pages.currentIndex(), 2)
        self.assertIsNone(ui._thread)
        self.assertEqual(ui.status_label.text(), '请先填写登录信息')


    def test_login_runs_in_worker_thread_and_reports_failure(self):
        import threading
        main_thread = threading.get_ident()
        called_from = []
        results = []
        def fake_login(*args):
            called_from.append(threading.get_ident())
            return None
        with patch('qtui.login.login', side_effect=fake_login), \
             patch('qtui.run_sports_upload') as upload:
            worker = WorkerThread({'USER_ID':'offline', 'PASSWORD':'test-only'})
            worker.task_finished.connect(lambda success, message: results.append((success, message)))
            worker.start()
            for _ in range(20):
                QTest.qWait(10)
                if results and not worker.isRunning():
                    break
            worker.wait(1000)
            self.assertNotEqual(called_from[0], main_thread)
            self.assertFalse(results[0][0])
            upload.assert_not_called()
            worker.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_named_route_saved_then_recalled_in_main_workspace(self):
        from src.route_library import RouteLibrary
        from src.route_library_dialog import RouteLibraryDialog
        from PySide6.QtCore import QTimer
        dialog = self.dialog()
        points = [{'latitude':31.028, 'longitude':121.44}, {'latitude':31.029, 'longitude':121.442}]
        dialog.map.set_route(points)
        dialog.name_input.setText('保存后调用')
        dialog.save_to_library()
        self.assertIn('已保存', dialog.status.text())
        dialog.reject()
        restored = RouteLibrary().load()
        self.assertEqual(restored[0]['points'], points)
        ui = SportsUploaderUI();ui.show()
        def choose():
            library = next(w for w in self.app.topLevelWidgets() if isinstance(w, RouteLibraryDialog) and w.isVisible())
            library.list.setCurrentRow(0)
            QTest.mouseClick(library.use_button, Qt.MouseButton.LeftButton)
        QTimer.singleShot(20, choose)
        QTest.mouseClick(ui.library_button, Qt.MouseButton.LeftButton)
        self.assertEqual(ui.route_points, points)
        self.assertEqual(ui.route_name, '保存后调用')
        self.assertTrue(ui.route_enabled.isChecked())
        self.assertEqual(json.loads(self.config_path.read_text())['自定义路线'], points)

    def test_switching_provider_preserves_route_history_and_reports_actual_load_state(self):
        class OfflineAMap(RouteMap):
            def __init__(self, points=None, parent=None, settings=None):
                super().__init__(points, parent)
        points = [{'latitude':31.028, 'longitude':121.44}, {'latitude':31.029, 'longitude':121.442}]
        settings = {'provider':'osm', 'key':'test-only', 'security_code':'test-only'}
        with patch('src.route_editor.load_map_settings', return_value=settings), \
             patch('src.route_editor.save_map_settings') as save, \
             patch('src.amap_view.AMapView', OfflineAMap):
            dialog = RouteEditorDialog(points);dialog.show();self.app.processEvents()
            original = [dict(p) for p in dialog.map.points]
            dialog.map.set_route(points + [{'latitude':31.03,'longitude':121.444}])
            history = dialog.map.history[:]
            edited = dialog.map.points[:]
            dialog.provider_box.setCurrentIndex(1)
            self.assertEqual(dialog.active_provider,'amap')
            self.assertIn('加载中',dialog.provider_badge.text())
            self.assertEqual(dialog.map.points,edited)
            self.assertEqual(dialog.map.history,history)
            dialog.map.map_status.emit('高德地图已加载')
            self.assertEqual(dialog.provider_badge.text(),'高德 · 已启用')
            dialog.map.map_status.emit('高德地图未能加载')
            self.assertIn('加载异常',dialog.provider_badge.text())
            dialog.provider_box.setCurrentIndex(0)
            self.assertEqual(dialog.active_provider,'osm')
            self.assertEqual(dialog.map.points,edited)
            dialog.map.undo()
            self.assertEqual(dialog.map.points,original)
            self.assertEqual(save.call_count,2)

    def test_cancel_missing_amap_credentials_keeps_free_map_selected(self):
        with patch('src.route_editor.load_map_settings', return_value={'provider':'osm','key':'test-only','security_code':''}), \
             patch('src.route_editor.MapSettingsDialog') as settings:
            settings.return_value.exec.return_value=QDialog.DialogCode.Rejected
            dialog=self.dialog();original=dialog.map
            dialog.provider_box.setCurrentIndex(1)
            self.assertEqual(dialog.provider_box.currentData(),'osm')
            self.assertEqual(dialog.active_provider,'osm')
            self.assertIs(dialog.map,original)
            self.assertIn('仍在使用免费地图',dialog.status.text())



if __name__ == '__main__':
    unittest.main()
