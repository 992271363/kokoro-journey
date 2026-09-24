import datetime
import os
import shutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFormLayout, QSpinBox, QDialogButtonBox,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QLineEdit, QSizePolicy, QSlider, QStyle, QStyleOptionSlider,
    QWidget, QScrollArea, QFrame, QListWidget, QStackedWidget
)

from util.config import Settings
from util import autostart
from ui.theme import apply_theme
from util.path import get_data_dir
from ui.widgets import AlwaysDownComboBox
from db.io import clear_all_data, clear_failed_queue
from ui.transfer import DataTransferDialog
from ui.wizard import FirstRunWizard
from util.state import update_state
from util.format import format_seconds_to_text
from util import le
from core.http_client import validate_proxy_address


class StepSlider(QSlider):
    _SNAP = 5

    def _snap(self, value):
        lo, hi = self.minimum(), self.maximum()
        return max(lo, min(hi, round(value / self._SNAP) * self._SNAP))

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.isSliderDown():
            snapped = self._snap(self.value())
            if snapped != self.value():
                self.setValue(snapped)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        snapped = self._snap(self.value())
        if snapped != self.value():
            self.setValue(snapped)


class ZoomDialog(QDialog):

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self._main_window = main_window
        self.setWindowTitle("调整列表缩放")
        self.setFixedSize(340, 140)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )

        self._original_zoom = int(Settings().get("tableZoom", 100))
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._apply_full_zoom)
        self._pending_zoom = self._original_zoom

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        self.slider = StepSlider(Qt.Horizontal)
        self.slider.setRange(75, 200)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(25)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(25)
        self.slider.setMinimumHeight(24)
        self.slider.setValue(self._original_zoom)

        self.spinbox = QSpinBox()
        self.spinbox.setRange(75, 200)
        self.spinbox.setSingleStep(5)
        self.spinbox.setSuffix("%")
        self.spinbox.setValue(self._original_zoom)
        self.spinbox.setFixedWidth(80)
        self.spinbox.setStyleSheet("""
            QSpinBox::up-button, QSpinBox::down-button {
                width: 22px;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                width: 10px;
                height: 10px;
            }
        """)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spinbox.valueChanged.connect(self._on_spinbox_changed)

        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.spinbox)
        layout.addLayout(row)

        labels = QHBoxLayout()
        labels.addWidget(QLabel("75%"))
        labels.addStretch()
        labels.addWidget(QLabel("200%"))
        layout.addLayout(labels)

        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self._on_reject)
        layout.addWidget(btn_box)

    def _on_slider_changed(self, value):
        self.spinbox.blockSignals(True)
        self.spinbox.setValue(value)
        self.spinbox.blockSignals(False)
        self._apply_live_zoom(value)
        self._pending_zoom = value
        self._debounce_timer.start()

    def _on_spinbox_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self._apply_live_zoom(value)
        self._pending_zoom = value
        self._debounce_timer.start()

    def _apply_full_zoom(self):
        self._apply_live_zoom(self._pending_zoom)

    def _apply_live_zoom(self, value):
        if self._main_window and hasattr(self._main_window, 'table_manager'):
            self._main_window.table_manager.apply_zoom(value / 100.0)

    def _on_accept(self):
        self._debounce_timer.stop()
        self._apply_live_zoom(self.slider.value())
        Settings().set("tableZoom", self.slider.value())
        self.accept()

    def _on_reject(self):
        self._debounce_timer.stop()
        self._apply_live_zoom(self._original_zoom)
        self.reject()


class CloseAskDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认关闭")
        self.setFixedSize(340, 150)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 12)
        layout.setSpacing(12)

        hint = QLabel("您希望关闭程序还是最小化到系统托盘？")
        layout.addWidget(hint)

        self.remember_check = QCheckBox("记住我的选择，不再询问")
        self.remember_check.setProperty("remember_bar", True)
        self.remember_check.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.remember_check)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_tray = QPushButton("最小化到托盘")
        self.btn_tray.setMinimumWidth(110)
        btn_layout.addWidget(self.btn_tray)

        btn_layout.addStretch()

        self.btn_exit = QPushButton("退出程序")
        self.btn_exit.setProperty("secondary", True)
        self.btn_exit.setMinimumWidth(90)
        btn_layout.addWidget(self.btn_exit)

        layout.addLayout(btn_layout)

        self.choice = None

        self.btn_tray.clicked.connect(self._choose_tray)
        self.btn_exit.clicked.connect(self._choose_exit)

    def _choose_tray(self):
        self.choice = "tray"
        self.accept()

    def _choose_exit(self):
        self.choice = "exit"
        self.accept()


class SettingsDialog(QDialog):
    """设置对话框：左侧分类导航 + 右侧对应设置内容。

    仅布局分层；所有设置控件仍在构造期建立，保存/重置/校验/联动逻辑不变。
    """

    def __init__(self, parent=None, app_start_time=None, total_runtime=0):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self._app_start_time = app_start_time
        self._base_runtime = total_runtime
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(12)

        self._nav = QListWidget()
        self._nav.setObjectName("settings_nav")
        self._nav.setFixedWidth(120)
        self._nav.addItems(["常规", "监控与同步", "云存档", "数据"])
        body.addWidget(self._nav)

        self._stack = QStackedWidget()
        body.addWidget(self._stack, stretch=1)
        layout.addLayout(body, stretch=1)

        self._build_page_general()
        self._build_page_monitor()
        self._build_page_cloud()
        self._build_page_data()

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        # --- 底部按钮（固定）---
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_reset = QPushButton("恢复默认设置")
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.setProperty("secondary", True)
        self.btn_reset.clicked.connect(self._on_reset_defaults)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch()

        self.btn_ok = QPushButton("确认")
        self.btn_ok.setFixedHeight(34)
        self.btn_ok.setFixedWidth(80)
        self.btn_ok.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("应用")
        self.btn_apply.setFixedHeight(34)
        self.btn_apply.setFixedWidth(80)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    # ---------------- 页面构建 ----------------

    @staticmethod
    def _make_page():
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(8, 12, 16, 16)
        box.setSpacing(12)
        return page, box

    def _add_page(self, page: QWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._stack.addWidget(scroll)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 600;")
        return label

    def _build_page_general(self):
        page, box = self._make_page()

        box.addWidget(self._section_title("启动与关闭"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self.combo_close_action = AlwaysDownComboBox()
        self.combo_close_action.addItem("每次询问", "ask")
        self.combo_close_action.addItem("最小化到托盘", "tray")
        self.combo_close_action.addItem("退出程序", "exit")

        saved = Settings().get("closeToTray")
        if saved == "tray":
            self.combo_close_action.setCurrentIndex(1)
        elif saved == "exit":
            self.combo_close_action.setCurrentIndex(2)
        else:
            self.combo_close_action.setCurrentIndex(0)

        form.addRow("点击关闭按钮时:", self.combo_close_action)

        self.check_autostart = QCheckBox("开机自动启动")
        if autostart.is_available():
            self.check_autostart.setChecked(autostart.is_enabled())
        else:
            self.check_autostart.setEnabled(False)
            self.check_autostart.setToolTip("打包为 exe 后可用")
        form.addRow(self.check_autostart)

        self.check_minimize_on_start = QCheckBox("启动时最小化")
        self.check_minimize_on_start.setChecked(Settings().get("minimizeOnStart", False))
        form.addRow(self.check_minimize_on_start)

        self.check_hide_on_pick = QCheckBox("拾取窗口时隐藏主窗口")
        self.check_hide_on_pick.setChecked(bool(Settings().get("hideWindowOnPick", True)))
        self.check_hide_on_pick.setToolTip("拾取窗口时临时隐藏主窗口，便于选取被主窗口挡住的窗口。")
        form.addRow(self.check_hide_on_pick)
        box.addLayout(form)

        box.addWidget(self._section_title("界面与外观"))
        appearance = QFormLayout()
        appearance.setContentsMargins(0, 0, 0, 0)

        self.check_show_tray = QCheckBox("显示系统托盘图标")
        self.check_show_tray.setToolTip("在系统托盘区显示图标，可快速唤出窗口。")
        self.check_show_tray.setChecked(bool(Settings().get("showTrayIcon", True)))
        appearance.addRow(self.check_show_tray)

        theme_label = QLabel("主题:")
        self.radio_light = QRadioButton("浅色模式")
        self.radio_dark = QRadioButton("深色模式")
        self.radio_system = QRadioButton("跟随系统")
        self.theme_group = QButtonGroup(self)
        self.theme_group.addButton(self.radio_light)
        self.theme_group.addButton(self.radio_dark)
        self.theme_group.addButton(self.radio_system)

        current_theme = Settings().get("themeMode", "system")
        if current_theme == "light":
            self.radio_light.setChecked(True)
        elif current_theme == "dark":
            self.radio_dark.setChecked(True)
        else:
            self.radio_system.setChecked(True)

        theme_layout = QHBoxLayout()
        theme_layout.addWidget(self.radio_light)
        theme_layout.addWidget(self.radio_dark)
        theme_layout.addWidget(self.radio_system)
        appearance.addRow(theme_label, theme_layout)

        time_format_label = QLabel("时间格式:")
        self.radio_fmt_chinese = QRadioButton("中文（39小时56分13秒）")
        self.radio_fmt_english = QRadioButton("英文（39h56m13s）")
        self.radio_fmt_numeric = QRadioButton("数字（39:56:13）")
        self.time_format_group = QButtonGroup(self)
        self.time_format_group.addButton(self.radio_fmt_chinese)
        self.time_format_group.addButton(self.radio_fmt_english)
        self.time_format_group.addButton(self.radio_fmt_numeric)

        current_format = Settings().get("timeFormat", "english")
        if current_format == "chinese":
            self.radio_fmt_chinese.setChecked(True)
        elif current_format == "numeric":
            self.radio_fmt_numeric.setChecked(True)
        else:
            self.radio_fmt_english.setChecked(True)

        time_format_layout = QVBoxLayout()
        time_format_layout.addWidget(self.radio_fmt_chinese)
        time_format_layout.addWidget(self.radio_fmt_english)
        time_format_layout.addWidget(self.radio_fmt_numeric)
        appearance.addRow(time_format_label, time_format_layout)

        self.btn_zoom = QPushButton("调整列表缩放...")
        self.btn_zoom.clicked.connect(self._open_zoom_dialog)
        appearance.addRow(self.btn_zoom)
        box.addLayout(appearance)

        box.addWidget(self._section_title("启动"))
        le_form = QFormLayout()
        le_form.setContentsMargins(0, 0, 0, 0)

        le_dir_row = QHBoxLayout()
        self.le_dir_edit = QLineEdit(str(Settings().get("leRootDir", "") or ""))
        self.le_dir_edit.setPlaceholderText("例如 D:\\LE")
        self.le_dir_edit.setReadOnly(True)
        btn_le_browse = QPushButton("浏览...")
        btn_le_browse.setFixedWidth(76)
        btn_le_browse.clicked.connect(self._on_pick_le_dir)
        btn_le_clear = QPushButton("清除")
        btn_le_clear.setFixedWidth(60)
        btn_le_clear.clicked.connect(self._on_clear_le_dir)
        le_dir_row.addWidget(self.le_dir_edit, stretch=1)
        le_dir_row.addWidget(btn_le_browse)
        le_dir_row.addWidget(btn_le_clear)
        le_form.addRow("Locale Emulator 文件夹:", le_dir_row)

        self.le_profile_combo = AlwaysDownComboBox()
        self.le_profile_combo.setToolTip(
            "从 Locale Emulator 配置里读取的区域配置；勾选“用 Locale Emulator 启动”的游戏使用它。")
        le_form.addRow("默认区域配置:", self.le_profile_combo)

        self.btn_le_test = QPushButton("测试启动...")
        self.btn_le_test.setToolTip("选择一个程序，用当前设置通过 Locale Emulator 启动，验证配置是否可用。")
        self.btn_le_test.clicked.connect(self._on_test_le_launch)
        le_form.addRow(self.btn_le_test)
        box.addLayout(le_form)

        le_hint = QLabel(
            "在游戏详情页勾选“用 Locale Emulator 启动”，或在主界面右键选择“本次用 Locale Emulator 启动”。"
            "标注“需管理员”的区域配置会在启动时请求系统授权。")
        le_hint.setWordWrap(True)
        le_hint.setProperty("role", "muted")
        box.addWidget(le_hint)

        self._reload_le_profiles()

        box.addWidget(self._section_title("列表交互"))
        interaction = QFormLayout()
        interaction.setContentsMargins(0, 0, 0, 0)

        self.radio_dbl_launch = QRadioButton("启动游戏")
        self.radio_dbl_detail = QRadioButton("查看进程详情")
        self.dbl_group = QButtonGroup(self)
        self.dbl_group.addButton(self.radio_dbl_launch)
        self.dbl_group.addButton(self.radio_dbl_detail)
        if str(Settings().get("tableDoubleClickAction", "launch")).lower() == "detail":
            self.radio_dbl_detail.setChecked(True)
        else:
            self.radio_dbl_launch.setChecked(True)

        dbl_layout = QHBoxLayout()
        dbl_layout.addWidget(self.radio_dbl_launch)
        dbl_layout.addWidget(self.radio_dbl_detail)
        interaction.addRow(QLabel("双击列表项:"), dbl_layout)
        box.addLayout(interaction)

        box.addStretch()
        self._add_page(page)

    def _build_page_monitor(self):
        page, box = self._make_page()

        box.addWidget(self._section_title("后台同步"))
        sync_form = QFormLayout()
        sync_form.setContentsMargins(0, 0, 0, 0)

        self._sync_enabled = bool(Settings().get("syncEnabled", True))
        self.check_sync_enabled = QCheckBox()
        self.check_sync_enabled.setChecked(self._sync_enabled)
        self.check_sync_enabled.setToolTip("勾选启用后台自动同步，取消勾选则整条设置变暗且不再自动同步。")
        self.check_sync_enabled.stateChanged.connect(self._on_sync_enabled_changed)

        self._sync_label = QLabel("同步间隔:")
        self.spin_sync_interval = QSpinBox()
        self.spin_sync_interval.setRange(10, 600)
        self.spin_sync_interval.setSuffix(" 秒")
        self.spin_sync_interval.setValue(int(Settings().get("syncIntervalSeconds", 60)))
        self.spin_sync_interval.setToolTip("后台同步检查间隔，范围 10–600 秒。")

        sync_inner = QHBoxLayout()
        sync_inner.setSpacing(4)
        sync_inner.addWidget(self.check_sync_enabled)
        sync_inner.addWidget(self._sync_label)

        sync_row = QHBoxLayout()
        sync_row.setSpacing(6)
        sync_row.addLayout(sync_inner)
        sync_row.addWidget(self.spin_sync_interval)
        sync_row.addStretch()
        sync_form.addRow(sync_row)
        box.addLayout(sync_form)
        self._apply_sync_enabled_state()

        box.addWidget(self._section_title("暂离检测"))
        idle_form = QFormLayout()
        idle_form.setContentsMargins(0, 0, 0, 0)

        self._idle_enabled = bool(Settings().get("idleEnabled", True))
        self.check_idle_enabled = QCheckBox()
        self.check_idle_enabled.setChecked(self._idle_enabled)
        self.check_idle_enabled.setToolTip("勾选启用暂离检测，取消勾选则整条设置变暗且暂离功能失效。")
        self.check_idle_enabled.stateChanged.connect(self._on_idle_enabled_changed)

        self._idle_label = QLabel("暂离状态所需时长:")
        self.spin_idle_threshold = QSpinBox()
        self.spin_idle_threshold.setRange(0, 30)
        self.spin_idle_threshold.setSuffix(" 分钟")
        self.spin_idle_threshold.setValue(int(Settings().get("idleThresholdSeconds", 300) // 60))
        self.spin_idle_threshold.setToolTip("无键鼠操作超过此时长视为暂离，暂停专注计时。设为 0 禁用。")

        idle_inner = QHBoxLayout()
        idle_inner.setSpacing(4)
        idle_inner.addWidget(self.check_idle_enabled)
        idle_inner.addWidget(self._idle_label)

        idle_row = QHBoxLayout()
        idle_row.setSpacing(6)
        idle_row.addLayout(idle_inner)
        idle_row.addWidget(self.spin_idle_threshold)
        idle_row.addStretch()
        idle_form.addRow(idle_row)

        self.check_idle_tip = QCheckBox("达到暂离时长时弹出提示")
        self.check_idle_tip.setChecked(bool(Settings().get("idleTipEnabled", False)))
        self.check_idle_tip.setToolTip("无操作达到上方时长时，弹出系统托盘提示。")
        idle_form.addRow(self.check_idle_tip)
        box.addLayout(idle_form)
        self._apply_idle_enabled_state()

        box.addStretch()
        self._add_page(page)

    def _build_page_cloud(self):
        page, box = self._make_page()

        box.addWidget(self._section_title("同步"))
        sync_form = QFormLayout()
        sync_form.setContentsMargins(0, 0, 0, 0)

        self.check_cloud_enabled = QCheckBox("启用云存档同步")
        self.check_cloud_enabled.setToolTip("关闭后不进行任何云存档操作。")
        self.check_cloud_enabled.setChecked(bool(Settings().get("cloudSaveEnabled", True)))
        sync_form.addRow(self.check_cloud_enabled)

        self.check_cloud_sync_login = QCheckBox("登录时同步存档")
        self.check_cloud_sync_login.setToolTip("登录后自动比对并同步云端与本地存档（不覆盖有改动的本地存档）。")
        self.check_cloud_sync_login.setChecked(bool(Settings().get("cloudSyncOnLogin", False)))
        sync_form.addRow(self.check_cloud_sync_login)

        self.check_cloud_auto_upload = QCheckBox("关闭游戏后自动上传")
        self.check_cloud_auto_upload.setToolTip("仅对在个人中心关联了应用的存档条目生效。")
        self.check_cloud_auto_upload.setChecked(bool(Settings().get("cloudAutoUploadOnClose", False)))
        sync_form.addRow(self.check_cloud_auto_upload)
        box.addLayout(sync_form)

        box.addWidget(self._section_title("网络代理"))
        proxy_form = QFormLayout()
        proxy_form.setContentsMargins(0, 0, 0, 0)

        self.check_cloud_use_proxy = QCheckBox("使用系统代理")
        self.check_cloud_use_proxy.setToolTip(
            "未勾选：直连（忽略系统代理）。\n"
            "勾选且地址留空：使用系统代理。\n"
            "勾选并填写地址：走该代理（host:port）。")
        self.check_cloud_use_proxy.setChecked(bool(Settings().get("useSystemProxy", False)))
        proxy_form.addRow(self.check_cloud_use_proxy)

        proxy_row = QHBoxLayout()
        self.proxy_address_edit = QLineEdit(str(Settings().get("proxyAddress", "") or ""))
        self.proxy_address_edit.setPlaceholderText("host:port")
        proxy_row.addWidget(self.proxy_address_edit, stretch=1)
        proxy_form.addRow("代理地址：", proxy_row)

        self.proxy_hint = QLabel("")
        self.proxy_hint.setStyleSheet("color: #dc2626; font-size: 12px;")
        self.proxy_hint.setVisible(False)
        proxy_form.addRow("", self.proxy_hint)

        self.check_cloud_use_proxy.toggled.connect(self.proxy_address_edit.setEnabled)
        self.proxy_address_edit.setEnabled(self.check_cloud_use_proxy.isChecked())
        self.proxy_address_edit.textChanged.connect(self._on_proxy_address_changed)
        box.addLayout(proxy_form)

        box.addStretch()
        self._add_page(page)

    def _build_page_data(self):
        page, box = self._make_page()

        box.addWidget(self._section_title("存储与维护"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(get_data_dir())
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit, stretch=1)

        self.btn_change_dir = QPushButton("更改...")
        self.btn_change_dir.setFixedWidth(70)
        self.btn_change_dir.clicked.connect(self._on_change_data_dir)
        path_layout.addWidget(self.btn_change_dir)
        form.addRow("存储位置:", path_layout)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_data_transfer = QPushButton("数据转移…")
        self.btn_data_transfer.clicked.connect(self._on_data_transfer)
        btn_row.addWidget(self.btn_data_transfer)

        self.btn_clear_data = QPushButton("清除所有数据")
        self.btn_clear_data.clicked.connect(self._on_clear_all)
        btn_row.addWidget(self.btn_clear_data)

        self.btn_clear_failed = QPushButton("清除失败队列")
        self.btn_clear_failed.clicked.connect(self._on_clear_failed)
        btn_row.addWidget(self.btn_clear_failed)

        form.addRow(btn_row)
        box.addLayout(form)

        box.addWidget(self._section_title("运行统计"))
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(6)

        self._label_current = QLabel("本次运行：计算中…")
        stats_layout.addWidget(self._label_current)

        self._label_total = QLabel("累计运行：计算中…")
        self._label_total.setProperty("role", "muted")
        stats_layout.addWidget(self._label_total)
        box.addLayout(stats_layout)

        box.addStretch()
        self._add_page(page)

        self._runtime_timer = QTimer(self)
        self._runtime_timer.timeout.connect(self._update_runtime_display)
        self._runtime_timer.start(1000)
        self._update_runtime_display()

    # ---------------- 逻辑（未改动） ----------------

    def _update_runtime_display(self):
        if self._app_start_time:
            session_secs = int((datetime.datetime.now() - self._app_start_time).total_seconds())
            self._label_current.setText(f"本次运行：{format_seconds_to_text(session_secs)}")
            total_secs = self._base_runtime + session_secs
            self._label_total.setText(f"累计运行：{format_seconds_to_text(total_secs)}")

    def _on_change_data_dir(self):
        old_dir = get_data_dir()
        wizard = FirstRunWizard(self, initial_path=old_dir, reconfigure=True)
        if wizard.exec() != QDialog.Accepted:
            return
        new_path = wizard.selected_path()

        if os.path.normcase(os.path.normpath(old_dir)) == os.path.normcase(os.path.normpath(new_path)):
            QMessageBox.information(self, "提示", "数据存储位置未改变。")
            return

        target_db = os.path.join(new_path, "local_client.db")
        if os.path.exists(target_db):
            box = QMessageBox(self)
            box.setWindowTitle("目标位置已存在数据库")
            box.setIcon(QMessageBox.Warning)
            box.setText(
                "目标目录中已存在数据库文件 local_client.db。\n请选择处理方式："
            )
            btn_use = box.addButton("使用目标位置的数据库", QMessageBox.AcceptRole)
            btn_overwrite = box.addButton(
                "用原先位置的数据库覆盖（生成备份）", QMessageBox.DestructiveRole
            )
            btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
            box.setDefaultButton(btn_cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_cancel or clicked is None:
                return
            mode = "use_target" if clicked is btn_use else "overwrite"
        else:
            mode = "move"

        Settings().set("dataDirectory", new_path)
        Settings().set("pendingDataMigration", {
            "from": old_dir,
            "to": new_path,
            "mode": mode,
        })
        update_state(new_path)
        self.path_edit.setText(new_path)

        reply = QMessageBox.question(
            self,
            "需要重启",
            "数据存储位置已更改，重启后将自动迁移数据。\n是否立即重启应用？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._restart_app()

    def _on_data_transfer(self):
        dialog = DataTransferDialog(self)
        dialog.exec()

    def _on_clear_all(self):
        reply = QMessageBox.warning(
            self,
            "确认清除",
            "确定要清除所有本地数据吗？\n\n"
            "这将删除所有监控记录、统计和会话历史。\n"
            "操作前会自动备份当前数据。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ok, msg = clear_all_data()
        if ok:
            QMessageBox.information(
                self,
                "已清除",
                f"{msg}\n\n应用将自动重启。",
            )
            self._restart_app()
        else:
            QMessageBox.critical(self, "清除失败", msg)

    def _on_clear_failed(self):
        ok, msg = clear_failed_queue()
        if ok:
            QMessageBox.information(self, "已清除", msg)
        else:
            QMessageBox.critical(self, "清除失败", msg)

    def _restart_app(self):
        import sys
        import os
        self.accept()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def _apply_idle_enabled_state(self):
        checked = self.check_idle_enabled.isChecked()
        self._idle_label.setEnabled(checked)
        self.spin_idle_threshold.setEnabled(checked)
        self.check_idle_tip.setEnabled(checked)

    def _on_idle_enabled_changed(self, state):
        self._apply_idle_enabled_state()
        Settings().set("idleEnabled", bool(state))

    def _apply_sync_enabled_state(self):
        checked = self.check_sync_enabled.isChecked()
        self._sync_label.setEnabled(checked)
        self.spin_sync_interval.setEnabled(checked)

    def _on_sync_enabled_changed(self, state):
        self._apply_sync_enabled_state()
        Settings().set("syncEnabled", bool(state))

    def _on_proxy_address_changed(self, text: str) -> None:
        ok, msg = validate_proxy_address(text)
        if ok:
            self.proxy_hint.setVisible(False)
            self.proxy_hint.setText("")
        else:
            self.proxy_hint.setText(msg)
            self.proxy_hint.setVisible(True)

    def _save_settings(self) -> bool:
        ok, msg = validate_proxy_address(self.proxy_address_edit.text())
        if self.check_cloud_use_proxy.isChecked() and not ok:
            QMessageBox.warning(self, "代理地址无效", msg)
            return False

        close_value = self.combo_close_action.currentData()
        if close_value == "ask":
            Settings().set("closeToTray", None)
        else:
            Settings().set("closeToTray", close_value)

        Settings().set("syncEnabled", self.check_sync_enabled.isChecked())
        Settings().set("syncIntervalSeconds", self.spin_sync_interval.value())

        try:
            mw = self.parent()
            if hasattr(mw, "sync_controller"):
                new_interval = self.spin_sync_interval.value()
                mw.sync_controller.set_interval(new_interval)
                if self.check_sync_enabled.isChecked():
                    mw.sync_controller.resume()
                else:
                    mw.sync_controller.pause()
        except Exception:
            pass

        Settings().set("idleEnabled", self.check_idle_enabled.isChecked())
        Settings().set("idleThresholdSeconds", self.spin_idle_threshold.value() * 60)
        Settings().set("idleTipEnabled", self.check_idle_tip.isChecked())
        Settings().set("showTrayIcon", self.check_show_tray.isChecked())
        Settings().set("hideWindowOnPick", self.check_hide_on_pick.isChecked())

        Settings().set("cloudSaveEnabled", self.check_cloud_enabled.isChecked())
        Settings().set("cloudSyncOnLogin", self.check_cloud_sync_login.isChecked())
        Settings().set("cloudAutoUploadOnClose", self.check_cloud_auto_upload.isChecked())
        Settings().set("useSystemProxy", self.check_cloud_use_proxy.isChecked())
        Settings().set("proxyAddress", self.proxy_address_edit.text().strip())

        Settings().set("leRootDir", self.le_dir_edit.text().strip())
        Settings().set("leProfileGuid", self.le_profile_combo.currentData() or "")
        Settings().set("tableDoubleClickAction",
                       "detail" if self.radio_dbl_detail.isChecked() else "launch")

        if autostart.is_available():
            if self.check_autostart.isChecked():
                autostart.enable()
            else:
                autostart.disable()

        Settings().set("minimizeOnStart", self.check_minimize_on_start.isChecked())

        if self.radio_light.isChecked():
            apply_theme("light")
        elif self.radio_dark.isChecked():
            apply_theme("dark")
        else:
            apply_theme("system")

        if hasattr(self.parent(), "_refresh_toolbar_icons"):
            self.parent()._refresh_toolbar_icons()

        if hasattr(self.parent(), "_apply_tray_visibility"):
            self.parent()._apply_tray_visibility()

        new_format = "english"
        if self.radio_fmt_chinese.isChecked():
            new_format = "chinese"
        elif self.radio_fmt_numeric.isChecked():
            new_format = "numeric"
        if new_format != Settings().get("timeFormat", "english"):
            Settings().set("timeFormat", new_format)
            if hasattr(self.parent(), "_refresh_table"):
                self.parent()._refresh_table(skip_width_hint=True)

        return True

    def _on_apply(self):
        self._save_settings()

    def _on_reset_defaults(self):
        """把设置页中的非数据项恢复为默认值（不动数据目录/位置/统计）。"""
        reply = QMessageBox.question(
            self,
            "恢复默认设置",
            "将把设置页中的所有选项恢复为默认值。\n"
            "不会影响数据库、存储位置和运行统计。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.combo_close_action.setCurrentIndex(0)
        if self.check_autostart.isEnabled():
            self.check_autostart.setChecked(False)
        self.check_minimize_on_start.setChecked(False)
        self.check_sync_enabled.setChecked(True)
        self.spin_sync_interval.setValue(60)
        self.check_idle_enabled.setChecked(True)
        self.spin_idle_threshold.setValue(5)
        self.check_idle_tip.setChecked(False)
        self.check_hide_on_pick.setChecked(True)
        self.check_show_tray.setChecked(True)
        self.check_cloud_enabled.setChecked(True)
        self.check_cloud_sync_login.setChecked(False)
        self.check_cloud_auto_upload.setChecked(False)
        self.check_cloud_use_proxy.setChecked(False)
        self.proxy_address_edit.setText("")
        self.le_dir_edit.clear()
        self._reload_le_profiles()
        self.radio_dbl_launch.setChecked(True)
        self.radio_system.setChecked(True)
        self.radio_fmt_english.setChecked(True)

        Settings().set("tableZoom", 100)
        mw = self.parent()
        if hasattr(mw, "table_manager"):
            try:
                mw.table_manager.apply_zoom(1.0)
            except Exception:
                pass

        self._save_settings()
        QMessageBox.information(self, "已恢复", "设置已恢复为默认值。")

    def _on_accept(self):
        if self._save_settings():
            self.accept()

    def _open_zoom_dialog(self):
        dialog = ZoomDialog(self, self.parent())
        dialog.exec()

    # ---------------- Locale Emulator ----------------

    def _on_pick_le_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择 Locale Emulator 文件夹", self.le_dir_edit.text() or "")
        if not path:
            return
        self.le_dir_edit.setText(os.path.normpath(path))
        self._reload_le_profiles()

    def _on_clear_le_dir(self):
        self.le_dir_edit.clear()
        self._reload_le_profiles()

    def _reload_le_profiles(self):
        """按当前 LE 文件夹重新读取区域配置，尽量保留已选中的那套。"""
        previous = (
            self.le_profile_combo.currentData()
            if self.le_profile_combo.count() else Settings().get("leProfileGuid", "")
        )
        self.le_profile_combo.clear()

        root = self.le_dir_edit.text().strip()
        profiles = le.parse_profiles(le.find_leconfig(root)) if root else []
        if not profiles:
            self.le_profile_combo.addItem("（未找到区域配置）", "")
            self.le_profile_combo.setEnabled(False)
            return

        self.le_profile_combo.setEnabled(True)
        for item in profiles:
            self.le_profile_combo.addItem(le.profile_label(item), item["guid"])

        index = next((i for i, p in enumerate(profiles)
                      if p["guid"] == le.normalize_guid(previous)), -1)
        self.le_profile_combo.setCurrentIndex(index if index >= 0
                                              else le.pick_default_index(profiles))

    def _on_test_le_launch(self):
        root = self.le_dir_edit.text().strip()
        guid = self.le_profile_combo.currentData() or ""
        ok, reason = le.check_ready(root, guid)
        if not ok:
            QMessageBox.warning(self, "无法测试", reason)
            return
        target, _ = QFileDialog.getOpenFileName(
            self, "选择要测试启动的程序", "", "程序 (*.exe)")
        if not target:
            return
        leproc = le.find_leproc(root)
        ok, err = le.launch_with_le(leproc, guid, target)
        if ok:
            QMessageBox.information(self, "已启动", "已通过 Locale Emulator 启动该程序。")
        else:
            QMessageBox.warning(self, "启动失败", err)
