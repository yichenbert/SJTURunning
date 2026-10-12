import sys
import os
import re
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QProgressBar, QFormLayout, QGroupBox, QDateTimeEdit,
    QMessageBox, QScrollArea, QSizePolicy, QCheckBox, QSpinBox, QDoubleSpinBox,
    QSpacerItem, QRadioButton, QButtonGroup, QFrame, QDialog, QStackedWidget
)
from PySide6.QtCore import QThread, Signal, QDateTime, Qt, QUrl, QEvent, QTimer
from PySide6.QtGui import QTextCursor, QFont, QColor, QTextCharFormat, QPalette, QBrush, QIcon, QDesktopServices

from src.main import run_sports_upload
import src.login as login
from src.config import load_config
from utils.auxiliary_util import SportsUploaderError, get_base_path
import src.config as config


from src.design import STYLE, card, label, RouteOverview
from src.route import normalize_route, route_distance, validate_route
from src.route_editor import RouteEditorDialog
from src.route_library import RouteLibrary
from src.route_library_dialog import RouteLibraryDialog
from src.dialogs import SummaryDialog, show_message

RESOURCES_SUB_DIR = "assets"

RESOURCES_FULL_PATH = os.path.join(get_base_path(), RESOURCES_SUB_DIR)

class WorkerThread(QThread):
    """
    工作线程，用于在后台执行跑步数据上传任务，避免UI冻结。
    """
    progress_update = Signal(int, int, str)
    log_output = Signal(str, str)
    task_finished = Signal(bool, str)

    def __init__(self, config_data):
        super().__init__()
        self.config_data = config_data

    def run(self):
        success = False
        message = "任务已完成。"
        try:
            self.log_output.emit("正在登录…", "info")
            if self.isInterruptionRequested():
                raise SportsUploaderError("任务已停止。")
            session = login.login(self.config_data["USER_ID"], self.config_data["PASSWORD"])
            if session is None:
                raise SportsUploaderError("登录失败，请检查账号密码。")
            self.config_data["SESSION"] = session
            success, message = run_sports_upload(
                self.config_data,
                progress_callback=self.progress_callback,
                log_cb=self.log_callback,
                stop_check_cb=self.isInterruptionRequested
            )
        except SportsUploaderError as e:
            self.log_output.emit(f"任务中断: {e}", "error")
            message = str(e)
            success = False
        except Exception as e:
            self.log_output.emit(f"发生未预期的错误: {e}", "error")
            message = f"未预期的错误: {e}"
            success = False
        finally:
            if self.isInterruptionRequested() and not success:
                 self.task_finished.emit(False, "任务已手动终止。")
            else:
                 self.task_finished.emit(success, message)

    def progress_callback(self, current, total, message):
        self.progress_update.emit(current, total, message)

    def log_callback(self, message, level):
        self.log_output.emit(message, level)


class SportsUploaderUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('workspace')
        self.setWindowTitle(f'SJTU RUN · 路线工作台 {config.global_version}')
        self.setWindowIcon(QIcon(os.path.join(RESOURCES_FULL_PATH, 'SJTURM.png')))
        self._thread = None
        self._help_window = None
        self.config = load_config()
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.setInterval(500)
        self._auto_save_timer.timeout.connect(self._auto_save_config)
        self.setStyleSheet(STYLE)
        self.init_ui()
        self.resize(1160, 880)
        self.setMinimumSize(960, 700)
        screen = QApplication.primaryScreen()
        if screen:
            geometry = self.frameGeometry()
            geometry.moveCenter(screen.availableGeometry().center())
            self.move(geometry.topLeft())

    def _spin(self, key, default, minimum, maximum, suffix='', decimal=False):
        spin = QDoubleSpinBox() if decimal else QSpinBox()
        spin.setRange(minimum, maximum)
        if decimal:
            spin.setDecimals(1)
            spin.setSingleStep(0.1)
        spin.setValue(self.config.get(key, default))
        spin.setSuffix(suffix)
        spin.setMinimumWidth(95)
        spin.valueChanged.connect(self._schedule_auto_save)
        return spin

    @staticmethod
    def _row(parent, *items):
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        for item in items:
            row.addWidget(label(item, 'muted') if isinstance(item, str) else item)
        parent.addWidget(widget)
        return widget

    def _switch_page(self, index):
        self.pages.setCurrentIndex(index)
        titles = [('路线与参数', '把路线、日期和配速安排好，再开始。'),
                  ('运行记录', '任务进度和运行结果，都在这里。'),
                  ('账号设置', '登录信息仅用于当前会话。')]
        self.page_title.setText(titles[index][0])
        self.page_subtitle.setText(titles[index][1])
        self.nav_buttons[index].setChecked(True)

    def init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 31, 22, 23)
        side.setSpacing(12)
        side.addWidget(label('SJTU RUN', 'brand'))
        side.addWidget(label('你的校园路线工作台', 'sidebarTitle'))
        side.addSpacing(32)
        side.addWidget(label('工作区', 'eyebrow'))
        self.nav_buttons = []
        navigation = QButtonGroup(self)
        navigation.setExclusive(True)
        for i, text in enumerate(('路线与参数', '运行记录', '账号设置')):
            button = QPushButton(text)
            button.setCheckable(True)
            navigation.addButton(button)
            button.toggled.connect(lambda checked, index=i: self._switch_page(index) if checked else None)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch()
        side.addWidget(label('让每条路线\n都清楚可见。', 'sidebarTitle'))
        side.addSpacing(12)
        self.info_button = QPushButton('关于这个程序')
        self.info_button.clicked.connect(self.show_info_dialog)
        side.addWidget(self.info_button)
        side.addWidget(label(f'桌面版  {config.global_version}', 'muted'))
        root.addWidget(sidebar)
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(28, 27, 28, 24)
        main.setSpacing(20)
        header = QHBoxLayout()
        title = QVBoxLayout()
        title.setSpacing(4)
        self.page_title = label('路线与参数', 'pageTitle')
        self.page_subtitle = label('把路线、日期和配速安排好，再开始。', 'muted')
        title.addWidget(self.page_title)
        title.addWidget(self.page_subtitle)
        header.addLayout(title)
        header.addStretch()
        header.addWidget(label('配置自动保存', 'badge'))
        main.addLayout(header)
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)
        route_scroll = QScrollArea()
        route_scroll.setWidgetResizable(True)
        route_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        route_page = QWidget()
        route_page.setObjectName('scrollContent')
        route_layout = QVBoxLayout(route_page)
        route_layout.setContentsMargins(0, 0, 8, 0)
        route_layout.setSpacing(18)
        route_scroll.setWidget(route_page)
        self.pages.addWidget(route_scroll)
        try:
            self.route_points = normalize_route(self.config.get('自定义路线', []))
        except SportsUploaderError:
            self.route_points = []
        self.route_name = str(self.config.get('路线名称', '我的路线'))
        self.route_library = RouteLibrary()
        try:
            self.route_library.seed_current(self.route_name, self.route_points)
        except (SportsUploaderError, OSError):
            pass  # Opening the library reports the error without blocking startup.
        hero, hero_layout = card(name='heroCard')
        hero_content = QHBoxLayout()
        hero_left = QVBoxLayout()
        hero_left.setSpacing(10)
        hero_left.addWidget(label('当前路线', 'eyebrow'))
        self.route_summary = label(self.route_name, 'routeTitle', True)
        hero_left.addWidget(self.route_summary)
        self.route_metric = label('0.000 公里', 'metric')
        hero_left.addWidget(self.route_metric)
        self.route_note = label('打开地图，沿道路绘制一条路线。', 'muted', True)
        hero_left.addWidget(self.route_note)
        hero_left.addStretch()
        self.route_enabled = QCheckBox('使用地图路线')
        self.route_enabled.setChecked(self.config.get('使用自定义路线', False))
        hero_left.addWidget(self.route_enabled)
        hero_content.addLayout(hero_left, 3)
        self.route_overview = RouteOverview()
        hero_content.addWidget(self.route_overview, 2)
        hero_layout.addLayout(hero_content)
        hero_actions = QHBoxLayout()
        hero_actions.addWidget(label('按实际路线长度计算距离', 'muted'))
        hero_actions.addStretch()
        self.route_button = QPushButton('打开路线画布')
        self.route_button.setObjectName('primary')
        self.route_button.clicked.connect(self.edit_route)
        self.library_button = QPushButton("我的路线")
        self.library_button.clicked.connect(self.open_route_library)
        hero_actions.addWidget(self.library_button)
        hero_actions.addWidget(self.route_button)
        hero_layout.addLayout(hero_actions)
        route_layout.addWidget(hero)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        date_card, dates = card('记录日期', '选择最近几天，或填写具体日期。')
        self.mode_days_radio = QRadioButton('最近几天')
        self.mode_dates_radio = QRadioButton('指定日期')
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_days_radio)
        self.mode_group.addButton(self.mode_dates_radio)
        self._row(dates, self.mode_days_radio, self.mode_dates_radio)
        self.days_spin = self._spin('跑步天数', 25, 1, 100, ' 天')
        self.days_widget = self._row(dates, '从昨天往前', self.days_spin)
        self.dates_widget = QWidget()
        date_entry = QVBoxLayout(self.dates_widget)
        date_entry.setContentsMargins(0, 0, 0, 0)
        date_entry.setSpacing(8)
        self.dates_input = QLineEdit(', '.join(self.config.get('指定日期列表', [])))
        self.dates_input.setPlaceholderText('2026-10-10, 2026-10-09')
        self.dates_input.textChanged.connect(self._schedule_auto_save)
        date_entry.addWidget(self.dates_input)
        date_entry.addWidget(label('多个日期用英文逗号隔开', 'muted'))
        dates.addWidget(self.dates_widget)
        self.mode_dates_radio.setChecked(self.config.get('指定日期模式', False))
        self.mode_days_radio.setChecked(not self.mode_dates_radio.isChecked())
        self.mode_days_radio.toggled.connect(self.on_mode_changed)
        self.mode_days_radio.toggled.connect(self._schedule_auto_save)
        self.on_mode_changed(True)
        dates.addSpacing(10)
        dates.addWidget(label('出发时间', 'cardTitle'))
        self.random_time_check = QCheckBox('在时间范围内随机选择')
        self.random_time_check.setChecked(self.config.get('跑步时间随机', False))
        dates.addWidget(self.random_time_check)
        self.fixed_hour_spin = self._spin('固定跑步时间_时', 8, 0, 23, ' 时')
        self.fixed_min_spin = self._spin('固定跑步时间_分', 0, 0, 59, ' 分')
        self.fixed_time_widget = self._row(dates, self.fixed_hour_spin, self.fixed_min_spin)
        self.rand_start_spin = self._spin('随机时间范围_开始时', 7, 0, 23, ' 时')
        self.rand_end_spin = self._spin('随机时间范围_结束时', 20, 0, 23, ' 时')
        self.random_time_widget = self._row(dates, self.rand_start_spin, '至', self.rand_end_spin)
        self.random_time_check.toggled.connect(self.on_time_mode_changed)
        self.random_time_check.toggled.connect(self._schedule_auto_save)
        self.on_time_mode_changed(self.random_time_check.isChecked())
        dates.addStretch()
        columns.addWidget(date_card, 1)
        pace_card, pace = card('距离与配速', '地图路线保持原样，配速可以自由设置。')
        self.random_params_check = QCheckBox('使用随机参数')
        self.random_params_check.setChecked(self.config.get('参数随机', False))
        pace.addWidget(self.random_params_check)
        self.fixed_params_widget = QWidget()
        fixed = QVBoxLayout(self.fixed_params_widget)
        fixed.setContentsMargins(0, 0, 0, 0)
        fixed.setSpacing(13)
        self.dist_spin = self._spin('每日距离_米', 5000, 1000, 20000, ' 米')
        self.route_distance_badge = label('', 'cardTitle')
        self._row(fixed, '距离', self.dist_spin, self.route_distance_badge)
        self.pace_spin = self._spin('配速_分钟每公里', 3.5, 3, 9, ' 分 / 公里', True)
        self._row(fixed, '配速', self.pace_spin)
        pace.addWidget(self.fixed_params_widget)
        self.random_params_widget = QWidget()
        ranges = QVBoxLayout(self.random_params_widget)
        ranges.setContentsMargins(0, 0, 0, 0)
        ranges.setSpacing(12)
        self.dist_min_spin = self._spin('距离最小_米', 4000, 1000, 20000)
        self.dist_max_spin = self._spin('距离最大_米', 6000, 1000, 20000)
        self.dist_range_widget = self._row(ranges, self.dist_min_spin, '至', self.dist_max_spin)
        self.pace_min_spin = self._spin('配速最小_分钟每公里', 3.5, 3, 9, '', True)
        self.pace_max_spin = self._spin('配速最大_分钟每公里', 5.0, 3, 9, '', True)
        self._row(ranges, self.pace_min_spin, '至', self.pace_max_spin)
        ranges.addWidget(label('配速单位：分钟 / 公里', 'muted'))
        pace.addWidget(self.random_params_widget)
        self.random_params_check.toggled.connect(self.on_params_mode_changed)
        self.random_params_check.toggled.connect(self._schedule_auto_save)
        self.on_params_mode_changed(self.random_params_check.isChecked())
        pace.addStretch()
        pace.addWidget(label('路线按绘制顺序走一遍，不会自动重复绕圈。', 'muted', True))
        columns.addWidget(pace_card, 1)
        route_layout.addLayout(columns)
        route_layout.addStretch()
        # Activity and account pages keep setup and long logs out of the route workspace.
        activity = QWidget()
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(0, 0, 0, 0)
        logs_card, logs = card('任务日志', '开始任务后，这里会显示每一步的结果。')
        self.log_output_area = QTextEdit()
        self.log_output_area.setReadOnly(True)
        self.log_output_area.setPlaceholderText('暂无运行记录')
        logs.addWidget(self.log_output_area, 1)
        activity_layout.addWidget(logs_card, 1)
        self.pages.addWidget(activity)
        account = QWidget()
        account_layout = QVBoxLayout(account)
        account_layout.setContentsMargins(0, 0, 0, 0)
        account_card, accounts = card('Jaccount 登录', '账号密码只用于本次登录，不写入配置文件。')
        form = QFormLayout()
        form.setVerticalSpacing(18)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('输入 Jaccount 用户名')
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('输入密码')
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('用户名', self.username_input)
        form.addRow('密码', self.password_input)
        accounts.addLayout(form)
        accounts.addSpacing(8)
        return_button = QPushButton('返回路线与参数')
        return_button.clicked.connect(lambda: self._switch_page(0))
        accounts.addWidget(return_button, 0, Qt.AlignmentFlag.AlignLeft)
        account_layout.addWidget(account_card)
        account_layout.addStretch()
        self.pages.addWidget(account)
        footer, foot = card(name='footer')
        foot.setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        status = QVBoxLayout()
        status.setSpacing(6)
        self.status_label = label('准备就绪', 'cardTitle')
        status.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(180)
        status.addWidget(self.progress_bar)
        row.addLayout(status, 1)
        row.addSpacing(24)
        self.stop_button = QPushButton('停止任务')
        self.stop_button.setObjectName('stopButton')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_upload)
        row.addWidget(self.stop_button)
        self.start_button = QPushButton('开始提交')
        self.start_button.setObjectName('startButton')
        self.start_button.setMinimumWidth(130)
        self.start_button.clicked.connect(self.start_upload)
        row.addWidget(self.start_button)
        foot.addLayout(row)
        main.addWidget(footer)
        root.addWidget(content, 1)
        self.route_enabled.toggled.connect(self.update_route_summary)
        self.route_enabled.toggled.connect(self._schedule_auto_save)
        self.update_route_summary()
        self._switch_page(0)

    def edit_route(self):
        dialog = RouteEditorDialog(self.route_points, self.route_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.route_points = dialog.selected_points
            self.route_name = dialog.selected_name
            self.route_enabled.setChecked(True)
            self.update_route_summary()
            self._auto_save_config()

    def open_route_library(self):
        dialog = RouteLibraryDialog(self, self.route_library)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            route = dialog.selected_route
            self.route_points = [dict(p) for p in route['points']]
            self.route_name = route['name']
            self.route_enabled.setChecked(True)
            self.update_route_summary()
            self._auto_save_config()

    def update_route_summary(self):
        enabled = self.route_enabled.isChecked()
        distance = route_distance(self.route_points)
        if self.route_points:
            self.route_summary.setText(self.route_name)
        else:
            self.route_summary.setText("还没有路线")
        for spin in (self.dist_spin, self.dist_min_spin, self.dist_max_spin):
            spin.setEnabled(not enabled)
            spin.setToolTip("使用自定义路线时，距离由路线长度决定。" if enabled else "")
        self.route_metric.setText(f"{distance / 1000:.3f} 公里")
        self.route_overview.set_points(self.route_points)
        self.dist_spin.setVisible(not enabled)
        self.route_distance_badge.setVisible(enabled)
        self.route_distance_badge.setText(f"{distance:.0f} 米")
        self.dist_range_widget.setVisible(not enabled)
        self.random_params_check.setText("在范围内随机选择配速" if enabled else "在范围内随机选择距离和配速")
        self.route_note.setText("按实际路线长度计算，保留每一个转弯。" if enabled else
                               "在地图上点选或手绘，保存你想跑的路线。")

    def on_mode_changed(self, checked):
        """模式切换：按天数 / 指定日期"""
        if self.mode_days_radio.isChecked():
            self.days_widget.show()
            self.dates_widget.hide()
        else:
            self.days_widget.hide()
            self.dates_widget.show()

    def on_time_mode_changed(self, use_random):
        """时间模式切换：随机 / 固定"""
        if use_random:
            self.fixed_time_widget.hide()
            self.random_time_widget.show()
        else:
            self.fixed_time_widget.show()
            self.random_time_widget.hide()

    def on_params_mode_changed(self, use_random):
        """参数模式切换：随机 / 固定"""
        if use_random:
            self.fixed_params_widget.hide()
            self.random_params_widget.show()
        else:
            self.fixed_params_widget.show()
            self.random_params_widget.hide()

    def _schedule_auto_save(self):
        """触发自动保存（带防抖）"""
        self._auto_save_timer.start()

    def _auto_save_config(self):
        """静默自动保存配置到 config.json（不弹出提示框）"""
        import json
        from src.config import get_config_path
        
        try:
            # 解析指定日期列表
            dates_text = self.dates_input.text().strip()
            dates_list = []
            if dates_text:
                dates_list = [d.strip() for d in dates_text.split(",") if d.strip()]
            
            new_config = {
                "// 说明": "SJTU 校园跑步工具配置文件",
                "使用自定义路线": self.route_enabled.isChecked(),
                "路线名称": self.route_name,
                "自定义路线": self.route_points,
                "指定日期模式": self.mode_dates_radio.isChecked(),
                "指定日期列表": dates_list,
                "跑步天数": self.days_spin.value(),
                "参数随机": self.random_params_check.isChecked(),
                "每日距离_米": self.dist_spin.value(),
                "配速_分钟每公里": self.pace_spin.value(),
                "距离最小_米": self.dist_min_spin.value(),
                "距离最大_米": self.dist_max_spin.value(),
                "配速最小_分钟每公里": self.pace_min_spin.value(),
                "配速最大_分钟每公里": self.pace_max_spin.value(),
                "GPS采样间隔_秒": 3,
                "跑步时间随机": self.random_time_check.isChecked(),
                "固定跑步时间_时": self.fixed_hour_spin.value(),
                "固定跑步时间_分": self.fixed_min_spin.value(),
                "随机时间范围_开始时": self.rand_start_spin.value(),
                "随机时间范围_结束时": self.rand_end_spin.value(),
                "起点纬度": self.route_points[0]["latitude"] if self.route_points else self.config.get("起点纬度", 31.031599),
                "起点经度": self.route_points[0]["longitude"] if self.route_points else self.config.get("起点经度", 121.442938),
                "终点纬度": self.route_points[-1]["latitude"] if self.route_points else self.config.get("终点纬度", 31.0264),
                "终点经度": self.route_points[-1]["longitude"] if self.route_points else self.config.get("终点经度", 121.4551)
            }
            
            self._current_app_config = new_config
            config_path = get_config_path()
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, ensure_ascii=False, indent=4)
            
            # 静默保存成功，不弹出提示框
        except Exception as e:
            # 自动保存失败时在日志中显示错误（不打扰用户）
            self.log_output_text(f"自动保存配置失败: {e}", "error")

    def get_settings_from_ui(self):
        """从UI获取当前配置并返回字典"""
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text()

            current_config = {
                "USER_ID": username,
                "PASSWORD": password,
                "START_LATITUDE": float(self.config.get("START_LATITUDE", 31.031599)),
                "START_LONGITUDE": float(self.config.get("START_LONGITUDE", 121.442938)),
                "END_LATITUDE": float(self.config.get("END_LATITUDE", 31.0264)),
                "END_LONGITUDE": float(self.config.get("END_LONGITUDE", 121.4551)),
                "RUNNING_SPEED_MPS": round(1000.0 / (3.5 * 60), 3),
                "INTERVAL_SECONDS": int(self.config.get("INTERVAL_SECONDS", 3)),
                "HOST": "pe.sjtu.edu.cn",
                "UID_URL": "https://pe.sjtu.edu.cn/sports/my/uid",
                "MY_DATA_URL": "https://pe.sjtu.edu.cn/sports/my/data",
                "POINT_RULE_URL": "https://pe.sjtu.edu.cn/api/running/point-rule",
                "UPLOAD_URL": "https://pe.sjtu.edu.cn/api/running/result/upload"
            }

            # START_TIME_EPOCH_MS 由后端生成，不从 UI 获取

            if not current_config["USER_ID"] or not current_config["PASSWORD"]:
                raise ValueError("用户名和密码不能为空。")

            from copy import deepcopy
            current_config["APP_CONFIG"] = deepcopy(self._current_app_config if hasattr(self, "_current_app_config") else load_config())
            if self.route_enabled.isChecked():
                points, _ = validate_route(self.route_points)
                current_config["APP_CONFIG"].update({"使用自定义路线": True, "自定义路线": points, "路线名称": self.route_name})
                current_config["START_LATITUDE"] = points[0]["latitude"]
                current_config["START_LONGITUDE"] = points[0]["longitude"]
            return current_config

        except ValueError as e:
            raise ValueError(f"输入错误: {e}")
        except Exception as e:
            raise Exception(f"获取配置时发生未知错误: {e}")

    def start_upload(self):
        if self._thread and self._thread.isRunning():
            return
        if not self.username_input.text().strip() or not self.password_input.text():
            self._switch_page(2)
            self.username_input.setFocus()
            self.status_label.setText("请先填写登录信息")
            return
        # 先确保配置已保存
        self._auto_save_config()
        
        # 构建配置摘要供用户确认
        if self.mode_dates_radio.isChecked():
            date_info = f"指定日期: {self.dates_input.text().strip() or '(未填写)'}"
        else:
            date_info = f"往前推 {self.days_spin.value()} 天"
        
        if self.random_params_check.isChecked():
            params_info = f"距离: {self.dist_min_spin.value()}~{self.dist_max_spin.value()} 米\n配速: {self.pace_min_spin.value()}~{self.pace_max_spin.value()} 分/km"
        else:
            params_info = f"距离: {self.dist_spin.value()} 米\n配速: {self.pace_spin.value()} 分/km"
        
        if self.random_time_check.isChecked():
            time_info = f"随机时间: {self.rand_start_spin.value()}:00 ~ {self.rand_end_spin.value()}:00"
        else:
            time_info = f"固定时间: {self.fixed_hour_spin.value():02d}:{self.fixed_min_spin.value():02d}"
        
        if self.route_enabled.isChecked():
            try:
                _, distance = validate_route(self.route_points)
            except SportsUploaderError as e:
                show_message(self, "请先绘制路线", str(e))
                return
            pace_info = (f"{self.pace_min_spin.value()}~{self.pace_max_spin.value()}" if self.random_params_check.isChecked()
                         else str(self.pace_spin.value()))
            params_info = f"地图路线: {self.route_name}\n路线距离: {distance:.1f} 米\n配速: {pace_info} 分/km"

        # 获取用户名
        username = self.username_input.text().strip() or "(未填写)"
        
        dialog = SummaryDialog('确认本次提交', [
            ('账号', username), ('记录日期', date_info),
            ('路线与配速', params_info), ('出发时间', time_info),
        ], self, '确认并开始')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.log_output_area.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("状态: 准备中...")
        self.log_output_text("准备开始上传...", "info")

        try:
            current_config_to_send = self.get_settings_from_ui()
        except (ValueError, Exception) as e:
            self.log_output_text(f"配置错误: {e}", "error")
            self.status_label.setText("状态: 错误")
            return

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.info_button.setEnabled(False)
        self.username_input.setEnabled(False)
        self.password_input.setEnabled(False)

        self._thread = WorkerThread(current_config_to_send)
        self._thread.progress_update.connect(self.update_progress)
        self._thread.log_output.connect(self.log_output_text)
        self._thread.task_finished.connect(self.upload_finished)
        self._thread.finished.connect(self._worker_done)
        self._switch_page(1)
        self._thread.start()

    def stop_upload(self):
        """请求工作线程停止。"""
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self.log_output_text("已发送停止请求，请等待任务清理并退出...", "warning")
            self.stop_button.setEnabled(False)
            self.status_label.setText("状态: 正在停止...")
        else:
            self.log_output_text("没有运行中的任务可以停止。", "info")


    def update_progress(self, current, total, message):
        """更新进度条和状态信息"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"状态: {message}")

    def log_output_text(self, message, level="info"):
        """将日志信息添加到文本区域，并根据级别着色"""
        cursor = self.log_output_area.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextCharFormat()
        if level == "error":
            format.setForeground(QColor("#DC3545"))
        elif level == "warning":
            format.setForeground(QColor("#FFA500"))
        elif level == "success":
            format.setForeground(QColor("#4CAF50"))
        else:
            format.setForeground(QColor("#333333"))

        # 如果是进度类短消息（例如: 已完成1/25），尝试替换最后一行以便在同一行更新
        try:
            if re.match(r"^已完成\d+/\d+", message):
                # 选择最后一段文本（最后一个 block）并检查是否包含“已完成”关键词
                doc = self.log_output_area.document()
                last_block = doc.lastBlock()
                if last_block.isValid() and "已完成" in last_block.text():
                    # 选中最后一个 block 并替换
                    cursor.movePosition(QTextCursor.End)
                    cursor.select(QTextCursor.BlockUnderCursor)
                    cursor.removeSelectedText()
                    # 插入新的进度信息（不额外换行），随后插入换行字符
                    cursor.insertText(f"[{level.upper()}] {message}\n", format)
                    self.log_output_area.ensureCursorVisible()
                    return
        except Exception:
            # 如果替换失败，退回到普通追加方式
            pass

        cursor.insertText(f"[{level.upper()}] {message}\n", format)
        self.log_output_area.ensureCursorVisible()

    def upload_finished(self, success, message):
        """上传任务完成后的处理"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.info_button.setEnabled(True)
        self.username_input.setEnabled(True)
        self.password_input.setEnabled(True)

        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)

        if success:
            self.status_label.setText("任务已完成")
            self.log_output_text(f"操作完成: {message}", "success")
            show_message(self, "上传结果", message)
        else:
            self.status_label.setText("任务未完成")
            self.log_output_text(f"操作失败: {message}", "error")

    def _worker_done(self):
        if self._thread and not self._thread.isRunning():
            self._thread.deleteLater()
            self._thread = None

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self.status_label.setText("正在停止任务，请稍后关闭")
            event.ignore()
            return
        super().closeEvent(event)

    def show_info_dialog(self):
        if self._help_window and self._help_window.isVisible():
            self._help_window.raise_()
            return
        dialog = QDialog(self)
        dialog.setObjectName('aboutDialog')
        dialog.setWindowTitle('关于 SJTU RUN')
        dialog.resize(520, 360)
        dialog.setStyleSheet(STYLE)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 28, 30, 25)
        layout.setSpacing(15)
        layout.addWidget(label('SJTU RUN', 'pageTitle'))
        layout.addWidget(label(f'路线工作台 · 桌面版 {config.global_version}', 'cardTitle'))
        layout.addWidget(label('在地图上规划路线，集中管理日期、配速和运行记录。支持 OpenStreetMap 和高德地图。', 'muted', True))
        layout.addWidget(label('参考源码：Gnonymous/SJTURunning\n原作者：Labyrinth0419 · 二改：accelerator-s · 三改：Gnonymous\n本版整理与发布：yichenbert · MIT License', 'muted', True))
        layout.addStretch()
        button = QPushButton('关闭')
        button.clicked.connect(dialog.close)
        layout.addWidget(button)
        self._help_window = dialog
        dialog.show()

if __name__ == "__main__":
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.global_version)
    ui = SportsUploaderUI()
    ui.show()
    sys.exit(app.exec())