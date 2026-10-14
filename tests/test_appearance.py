import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings, Qt, QCoreApplication, QEvent, QPoint
from PySide6.QtGui import QPalette, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from src.appearance import appearance, LIGHT, DARK, resolved_mode
from src.dialogs import SummaryDialog
from src.route_editor import RouteEditorDialog, RouteMap, project
from qtui import SportsUploaderUI


def contrast(a, b):
    def lum(value):
        rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(rgb,(.2126,.7152,.0722)))
    x,y=lum(a),lum(b)
    return (max(x,y)+.05)/(min(x,y)+.05)


class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.controller=appearance()
        self.old=(self.controller.preference,self.controller.settings)
        self.controller.settings=QSettings(str(Path(self.directory.name)/'appearance.ini'),QSettings.IniFormat)
        self.config_patch=patch('src.config.get_config_path',return_value=str(Path(self.directory.name)/'config.json'))
        self.map_patch=patch('src.route_editor.get_config_path',return_value=str(Path(self.directory.name)/'config.json'))
        self.tile_patch=patch.object(RouteMap,'_load_tile')
        for p in (self.config_patch,self.map_patch,self.tile_patch):p.start()

    def tearDown(self):
        for widget in self.app.topLevelWidgets():widget.close();widget.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.controller.preference,self.controller.settings=self.old
        self.controller.apply()
        for p in (self.config_patch,self.map_patch,self.tile_patch):p.stop()
        self.directory.cleanup()

    def test_system_signal_updates_existing_dialog_and_manual_override_is_respected(self):
        self.controller.set_preference('system')
        dialog=SummaryDialog('主题检查',[('日期','2026-10-14')]);dialog.show()
        for scheme, expected in ((Qt.ColorScheme.Dark,DARK),(Qt.ColorScheme.Light,LIGHT)):
            self.app.styleHints().colorSchemeChanged.emit(scheme);self.app.processEvents()
            self.assertEqual(dialog.palette().color(QPalette.Window).name(),expected['bg'])
            self.assertEqual(dialog.cancel_button.palette().color(QPalette.ButtonText).name(),expected['ink'])
        self.controller.set_preference('light')
        self.app.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        self.assertEqual(self.controller.mode,'light')
        self.assertEqual(self.controller.settings.value('mode'),'light')
        self.assertEqual(resolved_mode('system',Qt.ColorScheme.Dark),'dark')

    def test_theme_change_preserves_route_coordinates_map_geometry_and_click_alignment(self):
        editor=RouteEditorDialog();editor.show();self.app.processEvents()
        QTest.mouseClick(editor.map,Qt.LeftButton,pos=QPoint(200,180))
        QTest.mouseClick(editor.map,Qt.LeftButton,pos=QPoint(320,220))
        points=[dict(p) for p in editor.map.points];center=editor.map.center;zoom=editor.map.zoom
        geometry=editor.map.geometry()
        for mode in ('dark','light'):
            self.controller.set_preference(mode);self.app.processEvents()
            self.assertEqual(editor.map.geometry(),geometry)
            self.assertEqual(editor.map.points,points)
            self.assertEqual(editor.map.center,center);self.assertEqual(editor.map.zoom,zoom)
        QTest.mouseClick(editor.map,Qt.LeftButton,pos=QPoint(420,300))
        point=editor.map.points[-1]
        pixel=project(point['latitude'],point['longitude'],editor.map.zoom)-editor.map._origin()
        self.assertLess((pixel-QPoint(420,300)).manhattanLength(),.01)
        editor.map.shutdown()

    def test_existing_logs_recolor_and_new_logs_match_active_theme(self):
        ui=SportsUploaderUI();ui.show();self.app.processEvents()
        for level in ('info','warning','error','success'):ui.log_output_text('主题检查',level)
        for mode,colors in (('dark',DARK),('light',LIGHT)):
            ui.theme_box.setCurrentIndex(ui.theme_box.findData(mode));self.app.processEvents()
            block=ui.log_output_area.document().begin()
            for level in ('info','warning','error','success'):
                cursor=QTextCursor(block);cursor.movePosition(QTextCursor.NextCharacter)
                self.assertEqual(cursor.charFormat().foreground().color().name(),colors.get(level,colors['ink']))
                block=block.next()

    def test_text_status_and_selection_colors_meet_normal_text_contrast(self):
        for colors in (LIGHT,DARK):
            for key in ('ink','muted','accent','warning','error','success'):
                for bg in ('bg','surface','subtle'):
                    self.assertGreaterEqual(contrast(colors[key],colors[bg]),4.5,(key,bg))
            self.assertGreaterEqual(contrast(colors['accent'],colors['soft']),4.5)
