import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT_DIR))

import os
import datetime
from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QRadioButton, QButtonGroup, QFileDialog,
    QMessageBox, QTextEdit, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QDialogButtonBox, QWidget, QStackedWidget,
)

from db.io import export_data, import_data, preview_import_json, merge_import_json


class ExportWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            self.progress.emit("正在构建 JSON 数据...")
            ok, msg = export_data(self.filepath, "json")
            if ok:
                size = os.path.getsize(self.filepath)
                size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
                self.progress.emit(f"导出完成: {size_str}")
                self.finished.emit({"ok": True, "path": self.filepath, "size": size_str, "msg": msg})
            else:
                self.error.emit(msg)
        except Exception as e:
            self.error.emit(str(e))


class ImportWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, filepath: str, mode: str, dry_run: bool = False):
        super().__init__()
        self.filepath = filepath
        self.mode = mode
        self.dry_run = dry_run

    def run(self):
        try:
            if self.mode == "overwrite":
                self.progress.emit("正在覆盖导入，即将清空现有数据...")
                ok, msg = import_data(self.filepath)
                if ok:
                    self.finished.emit({"ok": True, "mode": "overwrite", "msg": msg})
                else:
                    self.error.emit(msg)
            else:
                if self.dry_run:
                    self.progress.emit("试运行模式：仅验证，不写入")
                else:
                    self.progress.emit("正在合并导入...")

                def cb(msg):
                    self.progress.emit(msg)

                ok, result = merge_import_json(
                    self.filepath,
                    dry_run=self.dry_run,
                    progress_callback=cb,
                )
                if ok:
                    result["mode"] = "merge"
                    if self.dry_run:
                        result["dry_run"] = True
                    self.finished.emit(result)
                else:
                    self.error.emit(result.get("error", "导入失败"))
        except Exception as e:
            self.error.emit(str(e))


class DataTransferDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据转移")
        self.resize(750, 600)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )

        self._thread = None
        self._worker = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 10)
        main_layout.setSpacing(10)

        mode_bar = QHBoxLayout()
        mode_bar.setSpacing(6)
        mode_bar.setAlignment(Qt.AlignLeft)

        self.btn_mode_export = QPushButton("导出 JSON")
        self.btn_mode_import = QPushButton("导入 JSON")
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for btn in (self.btn_mode_export, self.btn_mode_import):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setFixedWidth(100)
            mode_bar.addWidget(btn)
            self.mode_group.addButton(btn)

        self.btn_mode_export.setChecked(True)
        main_layout.addLayout(mode_bar)

        self._stack = QStackedWidget()
        self._panel_export = _ExportPanel(self)
        self._panel_import = _ImportPanel(self)
        self._stack.addWidget(self._panel_export)
        self._stack.addWidget(self._panel_import)
        main_layout.addWidget(self._stack, stretch=1)

        self.btn_mode_export.clicked.connect(
            lambda: (self._stack.setCurrentIndex(0), self.btn_mode_export.setChecked(True)))
        self.btn_mode_import.clicked.connect(
            lambda: (self._stack.setCurrentIndex(1), self.btn_mode_import.setChecked(True)))

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)


class _ExportPanel(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("保存到:"))
        self._path_label = QLabel()
        self._path_label.setObjectName("path_label")
        self._path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_row.addWidget(self._path_label, stretch=1)
        self._btn_browse = QPushButton("浏览...")
        self._btn_browse.setFixedWidth(70)
        self._btn_browse.clicked.connect(self._on_browse)
        path_row.addWidget(self._btn_browse)
        layout.addLayout(path_row)

        opt_group = QGroupBox("导出内容")
        opt_layout = QVBoxLayout(opt_group)
        self._chk_sessions = QCheckBox("包含会话记录 (ProcessSession)")
        self._chk_sessions.setChecked(True)
        self._chk_activities = QCheckBox("包含焦点活动详情 (FocusActivity)")
        self._chk_activities.setChecked(True)
        self._chk_daily = QCheckBox("包含日统计 (AppDailyUsage)")
        self._chk_daily.setChecked(True)
        opt_layout.addWidget(self._chk_sessions)
        opt_layout.addWidget(self._chk_activities)
        opt_layout.addWidget(self._chk_daily)
        layout.addWidget(opt_group)

        self._summary_label = QLabel("摘要: 选择目标路径后点击导出")
        self._summary_label.setObjectName("summary_label")
        layout.addWidget(self._summary_label)

        btn_row = QHBoxLayout()
        self._btn_export = QPushButton("导出")
        self._btn_export.setMinimumWidth(80)
        self._btn_export.clicked.connect(self._on_export)
        self._btn_reset = QPushButton("重置")
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_export)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximum(0)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(160)
        self._log.setPlaceholderText("操作日志将显示在此处...")
        layout.addWidget(self._log, stretch=1)

    def _on_browse(self):
        default_name = f"database_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON", default_name, "JSON 文件 (*.json)")
        if filepath:
            self._path_label.setText(filepath)

    def _on_export(self):
        filepath = self._path_label.text().strip()
        if not filepath:
            QMessageBox.warning(self, "提示", "请先选择目标文件路径")
            return

        self._set_ui_busy(True)
        self._log.clear()
        self._log.append("开始导出...")
        self._progress.setVisible(True)

        self._dialog._thread = QThread()
        self._dialog._worker = ExportWorker(filepath)
        self._dialog._worker.moveToThread(self._dialog._thread)
        self._dialog._thread.started.connect(self._dialog._worker.run)
        self._dialog._worker.progress.connect(self._append_log)
        self._dialog._worker.finished.connect(self._on_export_finished)
        self._dialog._worker.error.connect(self._on_export_error)
        self._dialog._worker.finished.connect(self._dialog._thread.quit)
        self._dialog._worker.error.connect(self._dialog._thread.quit)
        self._dialog._thread.finished.connect(
            self._dialog._worker.deleteLater)
        self._dialog._thread.start()

    def _on_export_finished(self, result):
        self._set_ui_busy(False)
        self._progress.setVisible(False)
        self._summary_label.setText(
            f"摘要: 已导出至 {result['path']} ({result['size']})")
        QMessageBox.information(self, "导出成功",
                                f"数据已导出到:\n{result['path']}")

    def _on_export_error(self, msg):
        self._set_ui_busy(False)
        self._progress.setVisible(False)
        self._log.append(f"[错误] {msg}")
        QMessageBox.critical(self, "导出失败", msg)

    def _on_reset(self):
        self._path_label.clear()
        self._summary_label.setText("摘要: 选择目标路径后点击导出")
        self._log.clear()
        self._progress.setVisible(False)

    def _set_ui_busy(self, busy):
        self._btn_export.setEnabled(not busy)
        self._btn_browse.setEnabled(not busy)
        self._btn_reset.setEnabled(not busy)
        self._chk_sessions.setEnabled(not busy)
        self._chk_activities.setEnabled(not busy)
        self._chk_daily.setEnabled(not busy)

    def _append_log(self, msg):
        self._log.append(msg)


class _ImportPanel(QWidget):
    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("源文件:"))
        self._path_label = QLabel()
        self._path_label.setObjectName("path_label")
        self._path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_row.addWidget(self._path_label, stretch=1)
        self._btn_browse = QPushButton("浏览...")
        self._btn_browse.setFixedWidth(70)
        self._btn_browse.clicked.connect(self._on_browse)
        path_row.addWidget(self._btn_browse)
        layout.addLayout(path_row)

        mode_group = QGroupBox("导入模式")
        mode_layout = QVBoxLayout(mode_group)
        self._radio_merge = QRadioButton("合并导入（按进程路径匹配，新增/更新）")
        self._radio_overwrite = QRadioButton("覆盖导入（清空现有数据后重建）")
        self._radio_merge.setChecked(True)
        mode_layout.addWidget(self._radio_merge)
        mode_layout.addWidget(self._radio_overwrite)
        layout.addWidget(mode_group)

        self._chk_dry_run = QCheckBox("试运行（仅验证解析，不写入数据库）")
        layout.addWidget(self._chk_dry_run)

        btn_row = QHBoxLayout()
        self._btn_preview = QPushButton("预览")
        self._btn_preview.setMinimumWidth(70)
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_import = QPushButton("导入")
        self._btn_import.setMinimumWidth(80)
        self._btn_import.clicked.connect(self._on_import)
        self._btn_reset = QPushButton("重置")
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_preview)
        btn_row.addWidget(self._btn_import)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(5)
        self._preview_table.setHorizontalHeaderLabels(
            ["应用名称", "焦点(小时)", "运行(小时)", "日记录数", "会话数"])
        self._preview_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        for c in range(1, 5):
            self._preview_table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._preview_table.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.setMaximumHeight(200)
        layout.addWidget(self._preview_table)

        self._summary_label = QLabel("摘要: 选择 JSON 文件后点击预览")
        self._summary_label.setObjectName("summary_label")
        layout.addWidget(self._summary_label)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximum(0)
        layout.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(160)
        self._log.setPlaceholderText("操作日志将显示在此处...")
        layout.addWidget(self._log, stretch=1)

    def _on_browse(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", "", "JSON 文件 (*.json)")
        if filepath:
            self._path_label.setText(filepath)

    def _on_preview(self):
        filepath = self._path_label.text().strip()
        if not filepath:
            QMessageBox.warning(self, "提示", "请先选择 JSON 文件")
            return

        self._log.clear()
        self._log.append("正在解析 JSON 文件...")

        result = preview_import_json(filepath)
        if "error" in result:
            self._log.append(f"[错误] {result['error']}")
            QMessageBox.critical(self, "预览失败", result["error"])
            return

        apps = result.get("apps", [])
        self._preview_table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            self._preview_table.setItem(
                row, 0, QTableWidgetItem(app["name"]))
            self._preview_table.setItem(
                row, 1, QTableWidgetItem(f"{app['focus_hours']:.1f}"))
            self._preview_table.setItem(
                row, 2, QTableWidgetItem(f"{app['lifetime_hours']:.1f}"))
            self._preview_table.setItem(
                row, 3, QTableWidgetItem(str(app["daily_count"])))
            self._preview_table.setItem(
                row, 4, QTableWidgetItem(str(app["session_count"])))

        self._summary_label.setText(
            f"摘要: {result['app_count']} 个应用, "
            f"{result['total_daily']} 条日统计, "
            f"{result['total_sessions']} 条会话记录")
        self._log.append(f"[OK] 解析完成: {result['app_count']} 个应用")

    def _on_import(self):
        filepath = self._path_label.text().strip()
        if not filepath:
            QMessageBox.warning(self, "提示", "请先选择 JSON 文件")
            return

        dry_run = self._chk_dry_run.isChecked()
        mode = "overwrite" if self._radio_overwrite.isChecked() else "merge"

        if not dry_run and mode == "overwrite":
            reply = QMessageBox.warning(
                self, "确认覆盖导入",
                "覆盖导入将清空现有所有数据后重建。\n\n操作前会自动备份。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self._set_ui_busy(True)
        self._log.clear()
        if dry_run:
            self._log.append("=== 试运行模式 ===")
        else:
            self._log.append("开始导入...")
        self._progress.setVisible(True)

        self._dialog._thread = QThread()
        self._dialog._worker = ImportWorker(filepath, mode, dry_run)
        self._dialog._worker.moveToThread(self._dialog._thread)
        self._dialog._thread.started.connect(self._dialog._worker.run)
        self._dialog._worker.progress.connect(self._append_log)
        self._dialog._worker.finished.connect(self._on_import_finished)
        self._dialog._worker.error.connect(self._on_import_error)
        self._dialog._worker.finished.connect(self._dialog._thread.quit)
        self._dialog._worker.error.connect(self._dialog._thread.quit)
        self._dialog._thread.finished.connect(
            self._dialog._worker.deleteLater)
        self._dialog._thread.start()

    def _on_import_finished(self, result):
        self._set_ui_busy(False)
        self._progress.setVisible(False)

        if result.get("dry_run"):
            self._log.append("\n[试运行完成] 未写入任何数据")
            QMessageBox.information(self, "试运行完成",
                                    "试运行结束，数据库未被修改。")
            return

        if result.get("mode") == "overwrite":
            msg = result.get("msg", "导入完成")
            self._log.append(f"\n[OK] {msg}")
            self._summary_label.setText("摘要: 导入完成")
            QMessageBox.information(self, "导入成功", msg)
            return

        bak = result.get("bak_path", "")
        msg_lines = [
            f"新增应用: {result.get('apps_added', 0)}",
            f"更新应用: {result.get('apps_updated', 0)}",
            f"日统计记录: {result.get('daily_upserted', 0)}",
        ]
        if bak:
            msg_lines.append(f"\n备份: {os.path.basename(bak)}")

        summary = "\n".join(msg_lines)
        self._log.append(f"\n[OK] 合并导入完成\n{summary}")
        self._summary_label.setText("摘要: 合并导入完成")
        QMessageBox.information(self, "导入成功", summary)

    def _on_import_error(self, msg):
        self._set_ui_busy(False)
        self._progress.setVisible(False)
        self._log.append(f"[错误] {msg}")
        QMessageBox.critical(self, "导入失败", msg)

    def _on_reset(self):
        self._path_label.clear()
        self._summary_label.setText("摘要: 选择 JSON 文件后点击预览")
        self._preview_table.setRowCount(0)
        self._log.clear()
        self._progress.setVisible(False)

    def _set_ui_busy(self, busy):
        self._btn_preview.setEnabled(not busy)
        self._btn_import.setEnabled(not busy)
        self._btn_browse.setEnabled(not busy)
        self._btn_reset.setEnabled(not busy)

    def _append_log(self, msg):
        self._log.append(msg)
