from src.appearance import bind_theme
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLineEdit, QFileDialog
from src.design import STYLE, label, RouteOverview
from src.dialogs import show_message
from src.route_library import RouteLibrary
from src.route import route_distance
from utils.auxiliary_util import SportsUploaderError


class RouteLibraryDialog(QDialog):
    def __init__(self, parent=None, library=None):
        super().__init__(parent)
        self.library = library or RouteLibrary()
        self.setWindowTitle('我的路线')
        bind_theme(self)
        self.resize(760, 560)
        layout = QVBoxLayout(self);layout.setContentsMargins(26,24,26,24);layout.setSpacing(14)
        layout.addWidget(label('我的路线', 'pageTitle'))
        layout.addWidget(label('选择已保存的路线，预览后直接调用。', 'muted'))
        body = QHBoxLayout()
        self.list = QListWidget();self.list.setMinimumWidth(280)
        body.addWidget(self.list,1)
        preview = QVBoxLayout();self.overview=RouteOverview();preview.addWidget(self.overview,1)
        self.details=label('还没有保存的路线', 'muted', True);preview.addWidget(self.details)
        self.name_input=QLineEdit();self.name_input.setPlaceholderText('路线名称');preview.addWidget(self.name_input)
        self.rename_button=QPushButton('重命名');self.rename_button.clicked.connect(self.rename);preview.addWidget(self.rename_button)
        body.addLayout(preview,1);layout.addLayout(body,1)
        footer=QHBoxLayout()
        self.import_button=QPushButton('导入以前的路线文件');self.import_button.clicked.connect(self.import_file);footer.addWidget(self.import_button)
        footer.addStretch()
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);footer.addWidget(cancel)
        self.use_button=QPushButton('使用这条路线');self.use_button.setObjectName('primary');self.use_button.clicked.connect(self.use_route);footer.addWidget(self.use_button)
        layout.addLayout(footer)
        self.list.currentRowChanged.connect(self.preview)
        self.list.itemDoubleClicked.connect(lambda _:self.use_route())
        self.reload()

    def reload(self, selected_id=None):
        self.list.clear()
        try:self.records=self.library.load()
        except SportsUploaderError as e:
            self.records=[];show_message(self,'路线库读取失败',str(e))
        selected=0
        for i,r in enumerate(self.records):
            item=QListWidgetItem(f"{r['name']}\n{route_distance(r['points'])/1000:.3f} 公里 · {len(r['points'])} 个节点")
            self.list.addItem(item)
            if r['id']==selected_id:selected=i
        self.list.setCurrentRow(selected if self.records else -1)
        self.preview(self.list.currentRow())

    def preview(self, index):
        valid=0<=index<len(getattr(self,'records',[]))
        self.use_button.setEnabled(valid);self.rename_button.setEnabled(valid);self.name_input.setEnabled(valid)
        if valid:
            r=self.records[index];self.name_input.setText(r['name']);self.overview.set_points(r['points'])
            self.details.setText(f"{route_distance(r['points'])/1000:.3f} 公里 · {len(r['points'])} 个节点\n保存在本机，重启后仍可调用。")
        else:self.overview.set_points([]);self.name_input.clear();self.details.setText('还没有保存的路线，可先导入已有文件。')

    def use_route(self):
        index=self.list.currentRow()
        if 0<=index<len(self.records):
            self.selected_route=self.records[index];self.accept()

    def rename(self):
        index=self.list.currentRow()
        if index<0:return
        try:
            route_id=self.records[index]['id'];self.library.rename(route_id,self.name_input.text());self.reload(route_id)
        except (SportsUploaderError,OSError) as e:show_message(self,'未能重命名',str(e))

    def import_file(self):
        filename,_=QFileDialog.getOpenFileName(self,'导入以前的路线','','路线文件 (*.json)')
        if not filename:return
        try:r=self.library.import_file(filename);self.reload(r['id'])
        except (SportsUploaderError,OSError,ValueError,KeyError,TypeError) as e:show_message(self,'导入失败',str(e))
