import datetime
import time
import os
import sys
import psutil
import win32gui
import win32con
import win32process
from PySide6.QtCore import Qt, QTimer, QSize, QObject, QEvent, Signal, QByteArray
from PySide6.QtGui import QAction, QIcon, QImage, QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QPushButton, QLabel,
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QSystemTrayIcon,
    QMenu, QStyle, QToolBar, QSizePolicy, QLineEdit, QButtonGroup
)

from db.repository import AppRepository
from ui.table import AppTableManager
from core.controller import MonitorController
from core.sync import SyncController
from util.config import Settings
from ui.settings import CloseAskDialog, SettingsDialog
from ui.widgets import StyledSizeGrip
from ui.picker import PickOverlay, PickButton
from ui.theme import get_system_theme
from util.search import make_search_keywords, matches_search_keywords

class _NoContextToolBar(QToolBar):
    def contextMenuEvent(self, event):
        pass

from ui.dialogs import AppDetailDialog, ClosingDialog, AddAppDialog
from ui.login import LoginDialog
from ui.stats import StatsDialog
from core.sync import get_and_prepare_sync_data, mark_sessions_as_synced
from core.api import send_data_to_api
from core.monitor import retry_failed_sessions, get_failed_queue_count


def _themed_icon(svg_path, color):
    with open(svg_path, "r", encoding="utf-8") as f:
        svg = f.read()
    svg = svg.replace("currentColor", color)
    data = QByteArray(svg.encode("utf-8"))
    image = QImage()
    if image.loadFromData(data, "SVG"):
        return QIcon(QPixmap.fromImage(image))
    return QIcon()


class PickRightClickBlocker(QObject):
    right_cancel_requested = Signal()

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.MouseButtonDblClick,
        ):
            if event.button() == Qt.RightButton:
                self.right_cancel_requested.emit()
                event.accept()
                return True

        if event.type() == QEvent.ContextMenu:
            self.right_cancel_requested.emit()
            event.accept()
            return True

        return False


class Mywindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # ---- UI 初始化 ----
        self.setWindowTitle("desktopActivitySystem")
        self.resize(1100, 619)

        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

# ---- 工具栏 ----
        toolbar = _NoContextToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(27, 27))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.setStyleSheet("""
            QToolBar {
                border: none;
                padding: 6px 8px;
                spacing: 6px;
                background: transparent;
            }

            QToolBar QToolButton {
                min-height: 48px;
                max-height: 48px;
                padding: 0 10px;
                margin: 0;
            }

            QToolBar QPushButton {
                min-height: 48px;
                max-height: 48px;
                padding: 0 12px;
                margin: 0;
            }

            QToolBar QLineEdit {
                min-height: 48px;
                max-height: 48px;
                padding: 0 10px;
                margin: 0;
            }

            QToolBar QLabel {
                min-height: 48px;
                max-height: 48px;
                padding: 0 8px;
                margin: 0;
            }
        """)

        if getattr(sys, 'frozen', False):
            self._base = sys._MEIPASS
        else:
            self._base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        base = self._base

        self.btn_monitor_toggle = QPushButton("暂停监控")
        self.btn_monitor_toggle.setToolTip("暂停/恢复全局监控")
        self.btn_monitor_toggle.setFixedHeight(48)
        toolbar.addWidget(self.btn_monitor_toggle)

        self.pushButton_procs = QPushButton("添加进程")
        self.pushButton_procs.setFixedHeight(48)
        toolbar.addWidget(self.pushButton_procs)

        self.btn_crosshair = PickButton("拾取窗口")
        self.btn_crosshair.setToolTip("按住后拖动到目标窗口上松开，自动添加监控")
        self.btn_crosshair.setProperty("crosshair", True)
        self.btn_crosshair.setFixedHeight(48)

        crosshair_path = os.path.join(base, "icons", "crosshair.svg")
        self.btn_crosshair.setIcon(_themed_icon(crosshair_path, "#16a34a"))
        self.btn_crosshair.setIconSize(QSize(27, 27))

        toolbar.addWidget(self.btn_crosshair)
        toolbar.addSeparator()

        # ---- 分组筛选按钮 ----
        self._current_group_id = None
        self.group_buttons = QButtonGroup(self)
        self.group_buttons.setExclusive(True)
        self._group_btn_container = QWidget()
        self._group_btn_layout = QHBoxLayout(self._group_btn_container)
        self._group_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._group_btn_layout.setSpacing(4)
        self._group_btn_container.setContextMenuPolicy(Qt.CustomContextMenu)
        self._group_btn_container.customContextMenuRequested.connect(self._on_group_context_menu)
        toolbar.addWidget(self._group_btn_container)
        self._rebuild_group_buttons()
        self.group_buttons.buttonClicked.connect(self._on_group_changed)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索名称...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(330)
        self.search_edit.setFixedHeight(48)
        self.search_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_edit.setToolTip("按应用名称或路径搜索，支持多个关键词")
        self.search_edit.setProperty("search", True)
        toolbar.addWidget(self.search_edit)

        self.btn_stats = QPushButton("统计")
        self.btn_stats.setFixedHeight(48)
        toolbar.addWidget(self.btn_stats)

        self.user_show = QLabel("未登录")
        self.user_show.setFixedHeight(48)
        self.user_show.setAlignment(Qt.AlignCenter)
        self.user_show.setStyleSheet("color: #64748b; font-size: 18px;")
        toolbar.addWidget(self.user_show)

        self.login_action = toolbar.addAction("登录")
        self.logout_action = toolbar.addAction("退出")
        self.logout_action.setVisible(False)

        self.settings_button = QPushButton()
        self.settings_button.setToolTip("设置")

        gear_path = os.path.join(base, "icons", "gear.svg")
        self.settings_button.setIcon(_themed_icon(gear_path, "#475569"))
        self.settings_button.setProperty("settings", True)
        self.settings_button.setFixedSize(48, 48)
        self.settings_button.setIconSize(QSize(27, 27))

        toolbar.addWidget(self.settings_button)

        self.addToolBar(toolbar)

        # ---- 表格 ----
        self._table_container = QWidget()
        table_layout = QVBoxLayout(self._table_container)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(0)

        self.tableWidget = QTableWidget()
        table_layout.addWidget(self.tableWidget, stretch=1)
        main_layout.addWidget(self._table_container, stretch=1)

        # ---- 状态 ----
        self.token = None
        self.username = None
        self._is_closing = False
        self._overlay = None
        self._settings = Settings()
        self._right_click_blocker = PickRightClickBlocker(self)
        self._right_click_blocker.right_cancel_requested.connect(
            self._request_pick_cancel_by_right
        )
        self._refresh_toolbar_icons()

        # ---- 组装子模块 ----
        self.table_manager = AppTableManager(self.tableWidget, self, self._settings)
        self.table_manager.detail_requested.connect(self._on_detail_requested)
        self.table_manager.launch_requested.connect(self._on_launch_requested)
        self.table_manager.watch_toggled_requested.connect(self._on_watch_toggled)
        self.table_manager.hard_delete_requested.connect(self._on_hard_delete_requested)
        self.table_manager.table_width_hint.connect(self._adjust_window_width)
        self._apply_table_zoom_from_settings()

        self.monitor_controller = MonitorController(self)
        self.monitor_controller.status_updated.connect(self.table_manager.update_status)
        self.monitor_controller.session_finished.connect(self._refresh_table)
        self.monitor_controller.session_save_failed.connect(self._on_session_save_failed)

        self.sync_controller = SyncController(token_provider=lambda: self.token, parent=self)
        self.sync_controller.status_updated.connect(self.update_status_bar)

        # 失败会话重试定时器（每 30 秒检查一次）
        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(30_000)
        self._retry_timer.timeout.connect(self._retry_failed_sessions)
        self._retry_timer.start()

        # ---- 系统托盘 ----
        self._setup_tray_icon()

        # ---- 信号连接 ----
        self.pushButton_procs.clicked.connect(self.open_add_app_dialog)
        self.btn_crosshair.pick_requested.connect(self.start_pick_window)
        self.search_edit.textChanged.connect(self._apply_table_search)
        self.btn_monitor_toggle.clicked.connect(self._toggle_monitor)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.login_action.triggered.connect(self.open_login_dialog)
        self.logout_action.triggered.connect(self._logout)
        self.btn_stats.clicked.connect(self.open_stats)

        # ---- 运行统计 ----
        self._app_start_time = datetime.datetime.now()

        # ---- 启动 ----
        self.statusBar().setSizeGripEnabled(False)
        self._size_grip = StyledSizeGrip(self.statusBar())
        self.statusBar().addPermanentWidget(self._size_grip)
        self.statusBar().showMessage("系统就绪，正在初始化...", 3000)

        self._refresh_table()
        self.monitor_controller.start(AppRepository.get_watched_apps_info())
        self.sync_controller.start()

        # 读取监控开关状态
        if not self._settings.get("monitorEnabled", True):
            self.monitor_controller.pause()
            self.btn_monitor_toggle.setText("恢复监控")
            self.btn_monitor_toggle.setProperty("paused", True)
            self.btn_monitor_toggle.setStyle(self.btn_monitor_toggle.style())
            self.statusBar().showMessage("监控已暂停")

    def _toggle_monitor(self):
        if self.monitor_controller.is_paused:
            self.monitor_controller.resume()
            self.btn_monitor_toggle.setText("暂停监控")
            self.btn_monitor_toggle.setProperty("paused", False)
            self.btn_monitor_toggle.setStyle(self.btn_monitor_toggle.style())
            self._settings.set("monitorEnabled", True)
            self.statusBar().showMessage("监控已恢复", 3000)
        else:
            self.monitor_controller.pause()
            self.btn_monitor_toggle.setText("恢复监控")
            self.btn_monitor_toggle.setProperty("paused", True)
            self.btn_monitor_toggle.setStyle(self.btn_monitor_toggle.style())
            self._settings.set("monitorEnabled", False)
            self.statusBar().showMessage("监控已暂停")

    def _setup_tray_icon(self):
        default_icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self._tray_icon = QSystemTrayIcon(default_icon, self)

        tray_menu = QMenu()
        action_show = tray_menu.addAction("显示主窗口")
        tray_menu.addSeparator()
        action_settings = tray_menu.addAction("设置...")
        tray_menu.addSeparator()
        action_exit = tray_menu.addAction("退出")

        action_show.triggered.connect(self._tray_show_window)
        action_settings.triggered.connect(self.open_settings_dialog)
        action_exit.triggered.connect(self._tray_exit_app)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._tray_show_window()

    def _tray_show_window(self):
        self.showNormal()
        self.activateWindow()

    def _tray_exit_app(self):
        self._is_closing = True
        self.close()

    def _rebuild_group_buttons(self):
        """重建分组筛选按钮。"""
        for btn in self.group_buttons.buttons():
            self.group_buttons.removeButton(btn)
        while self._group_btn_layout.count():
            item = self._group_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = AppRepository.get_all_groups()

        # 「全部」按钮
        btn_all = QPushButton("全部")
        btn_all.setCheckable(True)
        btn_all.setFixedHeight(32)
        btn_all.setProperty("group_btn", True)
        btn_all.setProperty("group_id", None)
        self.group_buttons.addButton(btn_all)
        self._group_btn_layout.addWidget(btn_all)
        if self._current_group_id is None:
            btn_all.setChecked(True)

        # 各分组按钮
        for gid, gname in groups:
            btn = QPushButton(gname)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setProperty("group_btn", True)
            btn.setProperty("group_id", gid)
            self.group_buttons.addButton(btn)
            self._group_btn_layout.addWidget(btn)
            if self._current_group_id == gid:
                btn.setChecked(True)

        # [+按钮] 管理分组
        btn_manage = QPushButton("+")
        btn_manage.setFixedHeight(32)
        btn_manage.setFixedWidth(32)
        btn_manage.setToolTip("管理分组")
        btn_manage.setProperty("group_btn", True)
        btn_manage.clicked.connect(self._open_group_dialog)
        self._group_btn_layout.addWidget(btn_manage)

    def _on_group_changed(self, btn):
        """分组按钮点击，切换筛选。"""
        gid = btn.property("group_id")
        self._current_group_id = gid
        self._refresh_table(skip_width_hint=True)

    def _on_group_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("管理分组...").triggered.connect(self._open_group_dialog)
        menu.exec(self._group_btn_container.mapToGlobal(pos))

    def _open_group_dialog(self):
        from ui.group import GroupDialog
        groups_before = AppRepository.get_all_groups()
        GroupDialog(self).exec()
        if AppRepository.get_all_groups() != groups_before:
            self._rebuild_group_buttons()
            self._refresh_table()

    def _refresh_table(self, skip_width_hint=False):
        apps = AppRepository.get_all_apps(group_filter=self._current_group_id)
        self.table_manager.refresh(apps, skip_width_hint=skip_width_hint)
        self._apply_table_search()

    def _apply_table_search(self):
        if not hasattr(self, "search_edit"):
            return
        keywords = make_search_keywords(self.search_edit.text())
        total = self.tableWidget.rowCount()
        matched = 0
        for row in range(total):
            if not keywords:
                self.tableWidget.setRowHidden(row, False)
                matched += 1
                continue
            values = []
            for col in range(self.tableWidget.columnCount()):
                item = self.tableWidget.item(row, col)
                values.append(item.text() if item is not None else "")
            visible = matches_search_keywords(values, keywords)
            self.tableWidget.setRowHidden(row, not visible)
            if visible:
                matched += 1
        if keywords:
            self.statusBar().showMessage(f"找到 {matched} 个匹配项", 2000)
        else:
            self.statusBar().clearMessage()

    def _adjust_window_width(self, table_content_width: int):
        margins = self._table_container.layout().contentsMargins()
        extra = margins.left() + margins.right()
        new_width = table_content_width + extra
        new_height = int(new_width * 9 / 16)
        screen = self.screen().availableGeometry()
        new_width = min(new_width, screen.width())
        new_height = min(new_height, screen.height())
        self.resize(new_width, new_height)

    def _refresh_monitor_list(self):
        self.monitor_controller.update_watch_list(AppRepository.get_watched_apps_info())

    def open_add_app_dialog(self):
        dialog = AddAppDialog(self)
        if dialog.exec() == QDialog.Accepted:
            selected_info = dialog.get_selected_info()
            if selected_info:
                exe_path, exe_name = selected_info
                if not AppRepository.app_exists(exe_path):
                    AppRepository.add_app(exe_path, exe_name)
                    self.statusBar().showMessage(f"已添加: {exe_name}", 3000)
                    self._refresh_table()
                    self._refresh_monitor_list()
                else:
                    self.statusBar().showMessage("该应用已在监控列表中", 3000)

    def _on_detail_requested(self, exe_path: str):
        app_data = AppRepository.get_app_by_path(exe_path)
        if app_data:
            dialog = AppDetailDialog(app_data, self)
            dialog.exec()

    def _on_launch_requested(self, launch_path: str):
        import os
        try:
            os.startfile(launch_path)
        except Exception:
            pass

    def _on_watch_toggled(self, exe_path: str, watched: bool):
        ok = AppRepository.set_app_watched(exe_path, watched)
        if not ok:
            return
        self.table_manager.set_row_watched_state(exe_path, watched)
        self._refresh_monitor_list()

    def _on_hard_delete_requested(self, exe_path: str, exe_name: str):
        ok = AppRepository.delete_app_completely(exe_path)
        if ok:
            self.monitor_controller.force_stop_tracking(exe_path)
            self.table_manager.table.setUpdatesEnabled(False)
            self._refresh_table()
            self.table_manager.table.setUpdatesEnabled(True)
            self._refresh_monitor_list()

    def start_pick_window(self):
        QApplication.instance().installEventFilter(self._right_click_blocker)

        self._pick_overlay = PickOverlay()
        self._pick_overlay.window_picked.connect(self._on_window_picked)
        self._pick_overlay.cancelled.connect(self.on_pick_cancelled)
        self._pick_overlay.show()
        QApplication.processEvents()
        self.statusBar().showMessage("请拖拽至目标窗口 | 右键或esc取消选取状态")

    def _remove_pick_right_click_blocker(self):
        try:
            QApplication.instance().removeEventFilter(self._right_click_blocker)
        except Exception:
            pass

    def _request_pick_cancel_by_right(self):
        if self._pick_overlay is not None:
            try:
                self._pick_overlay.request_cancel_by_right_button()
            except Exception:
                pass

    def on_pick_cancelled(self):
        self._remove_pick_right_click_blocker()
        QTimer.singleShot(0, lambda: self.statusBar().showMessage("已取消拾取", 2000))

    def _on_window_picked(self, hwnd):
        self._remove_pick_right_click_blocker()
        self.raise_()
        self.activateWindow()
        self._pick_hwnd(hwnd)

    def _pick_hwnd(self, hwnd):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            self.statusBar().showMessage("无法获取进程信息", 3000)
            return

        if pid in (0, 4):
            self.statusBar().showMessage("系统进程，已跳过", 3000)
            return

        try:
            proc = psutil.Process(pid)
            exe_path = proc.exe()
            exe_name = proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            self.statusBar().showMessage("无法读取进程路径", 3000)
            return

        if not exe_path:
            self.statusBar().showMessage("无法读取进程路径", 3000)
            return

        if not AppRepository.app_exists(exe_path):
            AppRepository.add_app(exe_path, exe_name)
            self.statusBar().showMessage(f"已添加: {exe_name}", 3000)
            self._refresh_table()
            self._refresh_monitor_list()
        else:
            self.statusBar().showMessage("该应用已在监控列表中", 3000)

    def open_login_dialog(self):
        print("[MainWindow] 打开登录对话框...")
        dialog = LoginDialog(self)
        result = dialog.exec()
        print(f"[MainWindow] 对话框返回值: {result}, QDialog.Accepted={QDialog.Accepted}")
        if result == QDialog.Accepted:
            print(f"[MainWindow] 登录成功, token={dialog.token[:10] if dialog.token else 'None'}..., username={dialog.username}")
            self.token = dialog.token
            self.username = dialog.username
            self.user_show.setText(self.username)
            self.user_show.setStyleSheet("padding: 4px 8px; color: #334155; font-size: 12px; font-weight: 500;")
            self.login_action.setVisible(False)
            self.logout_action.setVisible(True)
            print("[MainWindow] UI 已更新: 显示用户名, 隐藏登录按钮, 显示退出按钮")
            self.run_immediate_sync()
        else:
            print(f"[MainWindow] 登录对话框未返回 Accepted, 返回值: {result}")

    def _logout(self):
        print("[MainWindow] 用户点击退出登录")
        self.token = None
        self.username = None
        self.user_show.setText("未登录")
        self.user_show.setStyleSheet("padding: 4px 8px; color: #64748b; font-size: 12px;")
        self.login_action.setVisible(True)
        self.logout_action.setVisible(False)
        self.statusBar().showMessage("已退出登录", 3000)
        print("[MainWindow] 退出登录完成, UI 已恢复")

    def _refresh_toolbar_icons(self):
        mode = self._settings.get("themeMode", "system")
        if mode == "dark":
            is_dark = True
        elif mode == "system":
            is_dark = get_system_theme() == "dark"
        else:
            is_dark = False

        crosshair_color = "#6ee7b7" if is_dark else "#16a34a"
        gear_color = "#94a3b8" if is_dark else "#475569"

        self.btn_crosshair.setIcon(
            _themed_icon(os.path.join(self._base, "icons", "crosshair.svg"), crosshair_color)
        )
        self.settings_button.setIcon(
            _themed_icon(os.path.join(self._base, "icons", "gear.svg"), gear_color)
        )

    def open_settings_dialog(self):
        total_runtime = self._settings.get("appTotalRuntime", 0)
        SettingsDialog(self, self._app_start_time, total_runtime).exec()
        self._apply_table_zoom_from_settings()

    def _apply_table_zoom_from_settings(self):
        zoom = int(self._settings.get("tableZoom", 100))
        self.table_manager.apply_zoom(zoom / 100.0)

    def open_stats(self):
        StatsDialog(parent=self).exec()

    def run_immediate_sync(self):
        if not self.token:
            return
        data, sessions = get_and_prepare_sync_data()
        if data and send_data_to_api(data, "/sync/sessions/", self.token):
            mark_sessions_as_synced(sessions)
            self.update_status_bar("同步成功")

    def _on_session_save_failed(self, exe_name: str, error: str):
        count = get_failed_queue_count()
        self.statusBar().showMessage(
            f"⚠ 保存失败: {exe_name} — {error}（队列中 {count} 条待重试）", 8000
        )

    def _retry_failed_sessions(self):
        success, remaining = retry_failed_sessions()
        if success > 0:
            self._refresh_table()
            self.statusBar().showMessage(
                f"成功恢复 {success} 条会话记录，剩余 {remaining} 条待重试", 5000
            )
        elif remaining > 0:
            pass

    def update_status_bar(self, msg: str):
        self.statusBar().showMessage(msg, 5000)

    # ---- 关闭逻辑 ----
    def closeEvent(self, event):
        if self._is_closing:
            event.accept()
            return

        close_behavior = self._settings.get("closeToTray")

        if close_behavior is None:
            event.ignore()
            QTimer.singleShot(0, lambda: self._ask_close_behavior(event))
        elif close_behavior == "tray":
            event.ignore()
            self.hide()
        else:
            event.ignore()
            self._is_closing = True
            self._do_graceful_shutdown()

    def _ask_close_behavior(self, original_event):
        dialog = CloseAskDialog(self)
        dialog.exec()

        if dialog.choice == "tray":
            if dialog.remember_check.isChecked():
                self._settings.set("closeToTray", "tray")
            self.hide()
        elif dialog.choice == "exit":
            if dialog.remember_check.isChecked():
                self._settings.set("closeToTray", "exit")
            self._is_closing = True
            self._do_graceful_shutdown()
        else:
            pass

    def _do_graceful_shutdown(self):
        session_runtime = int((datetime.datetime.now() - self._app_start_time).total_seconds())
        if session_runtime > 0:
            total = self._settings.get("appTotalRuntime", 0) + session_runtime
            self._settings.set("appTotalRuntime", total)

        self._closing_dialog = ClosingDialog(self)
        self._closing_dialog.show()
        for _ in range(5):
            QApplication.processEvents()
            time.sleep(0.01)

        self._closing_dialog.set_status("正在停止进程监控...")
        self.monitor_controller.stop(
            timeout_ms=1500, dialog=self._closing_dialog, status_text="正在停止进程监控"
        )

        self._closing_dialog.set_status("正在停止同步服务...")
        self.sync_controller.stop(
            timeout_ms=3000, dialog=self._closing_dialog, status_text="正在停止同步服务"
        )

        self._closing_dialog.set_status("保存完成，正在关闭...")
        QApplication.processEvents()
        QTimer.singleShot(300, self._finish_close_event)

    def _finish_close_event(self):
        if self._closing_dialog:
            self._closing_dialog.close()
            self._closing_dialog = None
        self._tray_icon.hide()
        self.close()
