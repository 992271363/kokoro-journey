import os
import shutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QFormLayout, QSpinBox, QGroupBox, QDialogButtonBox,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QLineEdit, QSizePolicy, QSlider, QStyle, QStyleOptionSlider
)

from util.config import Settings
from util import autostart
from ui.theme import apply_theme
from util.path import get_data_dir
from ui.widgets import AlwaysDownComboBox
from db.io import clear_all_data, clear_failed_queue
from ui.transfer import DataTransferDialog


class StepSlider(QSlider):
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        snapped = round(self.value() / 25) * 25
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
        self.slider.setSingleStep(25)
        self.slider.setPageStep(25)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(25)
        self.slider.setValue(self._original_zoom)

        self.spinbox = QSpinBox()
        self.spinbox.setRange(75, 200)
        self.spinbox.setSingleStep(25)
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
        self._apply_live_zoom(value, live_preview=True)
        self._pending_zoom = value
        self._debounce_timer.start()

    def _on_spinbox_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self._apply_live_zoom(value, live_preview=True)
        self._pending_zoom = value
        self._debounce_timer.start()

    def _apply_full_zoom(self):
        self._apply_live_zoom(self._pending_zoom, live_preview=False)

    def _apply_live_zoom(self, value, live_preview=False):
        if self._main_window and hasattr(self._main_window, 'table_manager'):
            self._main_window.table_manager.apply_zoom(value / 100.0, live_preview)

    def _on_accept(self):
        self._debounce_timer.stop()
        self._apply_live_zoom(self.slider.value(), live_preview=False)
        Settings().set("tableZoom", self.slider.value())
        self.accept()

    def _on_reject(self):
        self._debounce_timer.stop()
        self._apply_live_zoom(self._original_zoom, live_preview=False)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(380)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(10)

        # --- 关闭行为 ---
        close_group = QGroupBox("关闭行为")
        close_form = QFormLayout(close_group)
        close_form.setContentsMargins(10, 18, 10, 8)

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

        close_form.addRow("点击关闭按钮时:", self.combo_close_action)
        layout.addWidget(close_group)

        # --- 通用 ---
        general_group = QGroupBox("通用")
        general_form = QFormLayout(general_group)
        general_form.setContentsMargins(10, 16, 10, 8)

        self.check_autostart = QCheckBox("开机自动启动")
        if autostart.is_available():
            self.check_autostart.setChecked(autostart.is_enabled())
        else:
            self.check_autostart.setEnabled(False)
            self.check_autostart.setToolTip("打包为 exe 后可用")
        general_form.addRow(self.check_autostart)

        self.spin_sync_interval = QSpinBox()
        self.spin_sync_interval.setRange(10, 600)
        self.spin_sync_interval.setSuffix(" 秒")
        self.spin_sync_interval.setValue(60)
        self.spin_sync_interval.setEnabled(False)
        self.spin_sync_interval.setToolTip("待实现")
        general_form.addRow("同步间隔:", self.spin_sync_interval)

        layout.addWidget(general_group)

        # --- 显示 ---
        display_group = QGroupBox("显示")
        display_form = QFormLayout(display_group)
        display_form.setContentsMargins(10, 16, 10, 8)

        self.check_show_tray = QCheckBox("显示系统托盘图标")
        self.check_show_tray.setEnabled(False)
        self.check_show_tray.setToolTip("待实现")
        self.check_show_tray.setChecked(True)
        display_form.addRow(self.check_show_tray)

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
        display_form.addRow(theme_label, theme_layout)

        self.btn_zoom = QPushButton("调整列表缩放...")
        self.btn_zoom.clicked.connect(self._open_zoom_dialog)
        display_form.addRow(self.btn_zoom)

        layout.addWidget(display_group)

        # --- 数据 ---
        data_group = QGroupBox("数据")
        data_form = QFormLayout(data_group)
        data_form.setContentsMargins(10, 16, 10, 8)

        # 当前数据目录
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(get_data_dir())
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit, stretch=1)

        self.btn_change_dir = QPushButton("更改...")
        self.btn_change_dir.setFixedWidth(70)
        self.btn_change_dir.clicked.connect(self._on_change_data_dir)
        path_layout.addWidget(self.btn_change_dir)
        data_form.addRow("存储位置:", path_layout)

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

        data_form.addRow(btn_row)

        layout.addWidget(data_group)

        layout.addStretch()

        # --- 底部按钮 ---
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_change_data_dir(self):
        current = get_data_dir()
        new_path = QFileDialog.getExistingDirectory(
            self, "选择新的数据存储目录", current
        )
        if not new_path:
            return
        new_path = os.path.normpath(os.path.abspath(new_path))
        if new_path == current:
            return

        # 检查目标目录是否已有数据文件
        has_existing = any(
            os.path.exists(os.path.join(new_path, f))
            for f in ["local_client.db", "failed_sessions.json"]
        )
        if has_existing:
            reply = QMessageBox.question(
                self,
                "目录不为空",
                "目标目录已存在数据文件，是否覆盖？\n\n"
                "选择「是」将覆盖现有文件。\n"
                "选择「否」则仅更改路径，不迁移数据。",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            migrate = (reply == QMessageBox.Yes)
        else:
            migrate = QMessageBox.question(
                self,
                "迁移数据",
                f"是否将现有数据迁移到新目录？\n\n"
                f"从：{current}\n"
                f"到：{new_path}",
                QMessageBox.Yes | QMessageBox.No,
            ) == QMessageBox.Yes

        if migrate:
            try:
                os.makedirs(new_path, exist_ok=True)
                for filename in ["local_client.db", "failed_sessions.json"]:
                    src = os.path.join(current, filename)
                    if os.path.exists(src):
                        shutil.copy2(src, new_path)
            except Exception as e:
                QMessageBox.critical(self, "迁移失败", f"无法复制数据文件：\n{e}")
                return

        Settings().set("dataDirectory", new_path)
        self.path_edit.setText(new_path)
        reply = QMessageBox.question(
            self,
            "需要重启",
            "数据存储位置已更改，是否立即重启应用？",
            QMessageBox.Yes | QMessageBox.No,
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

    def _on_accept(self):
        close_value = self.combo_close_action.currentData()
        if close_value == "ask":
            Settings().set("closeToTray", None)
        else:
            Settings().set("closeToTray", close_value)

        if autostart.is_available():
            if self.check_autostart.isChecked():
                autostart.enable()
            else:
                autostart.disable()

        if self.radio_light.isChecked():
            apply_theme("light")
        elif self.radio_dark.isChecked():
            apply_theme("dark")
        else:
            apply_theme("system")

        if hasattr(self.parent(), "_refresh_toolbar_icons"):
            self.parent()._refresh_toolbar_icons()

        self.accept()

    def _open_zoom_dialog(self):
        dialog = ZoomDialog(self, self.parent())
        dialog.exec()
