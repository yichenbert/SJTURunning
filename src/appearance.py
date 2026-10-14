"""Application-wide appearance, independent from route and account settings."""
from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = dict(bg='#ffffff', sidebar='#f7f7f8', surface='#ffffff', subtle='#f5f5f5',
             ink='#202123', muted='#60646c', border='#dedee3', hover='#ececef',
             accent='#315cce', soft='#edf2ff', error='#a62532', warning='#865400', success='#176b43')
DARK = dict(bg='#181818', sidebar='#212121', surface='#202020', subtle='#292929',
            ink='#ececec', muted='#b3b3bc', border='#434348', hover='#333336',
            accent='#a6bbff', soft='#29334b', error='#ffadb5', warning='#f5cf84', success='#8adbb1')


def resolved_mode(preference, scheme):
    return ('dark' if scheme == Qt.ColorScheme.Dark else 'light') if preference == 'system' else preference


class Appearance(QObject):
    changed = Signal()
    def __init__(self, app, settings=None):
        super().__init__(app)
        self.app = app
        self.settings = settings if settings is not None else QSettings('SJTURunPlus', 'Appearance')
        saved = self.settings.value('mode', 'system')
        self.preference = saved if saved in ('system', 'light', 'dark') else 'system'
        self.app.styleHints().colorSchemeChanged.connect(self._system_changed)
        self.apply()

    @property
    def colors(self):
        return DARK if self.mode == 'dark' else LIGHT

    def set_preference(self, preference):
        if preference not in ('system', 'light', 'dark'):
            raise ValueError('Unknown appearance mode')
        self.preference = preference
        self.settings.setValue('mode', preference)
        self.apply()

    def _system_changed(self, scheme):
        if self.preference == 'system':
            self.apply(scheme)

    def apply(self, scheme=None):
        self.mode = resolved_mode(self.preference, self.app.styleHints().colorScheme() if scheme is None else scheme)
        c = self.colors
        palette = QPalette()
        for role, key in ((QPalette.Window, 'bg'), (QPalette.WindowText, 'ink'),
                          (QPalette.Base, 'surface'), (QPalette.AlternateBase, 'subtle'),
                          (QPalette.Text, 'ink'), (QPalette.Button, 'surface'),
                          (QPalette.ButtonText, 'ink'), (QPalette.ToolTipBase, 'surface'),
                          (QPalette.ToolTipText, 'ink'), (QPalette.Highlight, 'soft'),
                          (QPalette.HighlightedText, 'accent'), (QPalette.PlaceholderText, 'muted'),
                          (QPalette.Link, 'accent')):
            palette.setColor(role, QColor(c[key]))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, QColor(c['muted']))
        self.app.setPalette(palette)
        from src.design import stylesheet
        self.app.setStyleSheet(stylesheet(c))
        for widget in self.app.topLevelWidgets():
            widget.update()
        self.changed.emit()


def appearance():
    app = QApplication.instance()
    if not hasattr(app, '_appearance'):
        app._appearance = Appearance(app)
    return app._appearance


def bind_theme(widget):
    # Global QSS also themes dialogs opened after a system appearance change.
    appearance()
    widget.setStyleSheet('')
