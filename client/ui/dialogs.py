from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QFrame, QDialogButtonBox,
    QVBoxLayout, QProgressBar, QPushButton, QHBoxLayout, QFileDialog
)
from PySide6.QtGui import QFont
import os

from db.models import WatchedApplication
from util.format import format_seconds_to_text
from ui.proc import ProcSelectDialog


class AddAppDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加监控应用")
        self.setFixedSize(320, 140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        hint = QLabel("请选择添加方式：")
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_from_process = QPushButton("从运行进程选择")
        self.btn_from_process.setMinimumHeight(36)
        btn_layout.addWidget(self.btn_from_process)

        self.btn_from_file = QPushButton("从本地文件选择")
        self.btn_from_file.setMinimumHeight(36)
        btn_layout.addWidget(self.btn_from_file)

        layout.addLayout(btn_layout)

        self.selected_info = None

        self.btn_from_process.clicked.connect(self._choose_from_process)
        self.btn_from_file.clicked.connect(self._choose_from_file)

    def _choose_from_process(self):
        dialog = ProcSelectDialog(self)
        if dialog.exec() == QDialog.Accepted:
            info = dialog.get_selected_proc_info()
            if info:
                self.selected_info = info
                self.accept()
            else:
                self.reject()
        else:
            self.reject()

    def _choose_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择可执行文件", "",
            "可执行文件 (*.exe *.bat *.cmd *.ps1 *.vbs);;所有文件 (*.*)"
        )
        if file_path:
            exe_name = os.path.splitext(os.path.basename(file_path))[0]
            self.selected_info = (file_path, exe_name)
            self.accept()
        else:
            self.reject()

    def get_selected_info(self):
        return self.selected_info


class AppDetailDialog(QDialog):
    def __init__(self, app_data: WatchedApplication, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"详细信息 - {os.path.splitext(app_data.executable_name)[0]}")
        self.resize(400, 300)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setContentsMargins(30, 20, 30, 20)
        name_without_ext = os.path.splitext(app_data.executable_name)[0]
        layout.addRow("<b>应用名称:</b>", QLabel(name_without_ext))

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addRow(line)

        layout.addRow("进程路径:", QLabel(app_data.executable_path))
        layout.addRow("启动路径:", QLabel(app_data.launch_path or app_data.executable_path))

        line_path = QFrame()
        line_path.setFrameShape(QFrame.HLine)
        layout.addRow(line_path)

        summary = app_data.summary

        def fmt_time(dt):
            return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "从未"

        layout.addRow("总焦点时长:", QLabel(format_seconds_to_text(summary.total_focus_time_seconds)))
        layout.addRow("总运行时长:", QLabel(format_seconds_to_text(summary.total_lifetime_seconds)))

        ratio = 0
        if summary.total_lifetime_seconds > 0:
            ratio = (summary.total_focus_time_seconds / summary.total_lifetime_seconds) * 100
        layout.addRow("焦点时长占比:", QLabel(f"{ratio:.1f}%"))

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        layout.addRow(line2)

        layout.addRow("首次启动:", QLabel(fmt_time(summary.first_seen_at)))
        layout.addRow("最后启动:", QLabel(fmt_time(summary.last_seen_start_at)))
        layout.addRow("最后结束:", QLabel(fmt_time(summary.last_seen_end_at)))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class ClosingDialog(QDialog):
    """关闭时的提示对话框，显示保存进度"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在关闭")
        self.setFixedSize(320, 140)
        # 去掉问号按钮，保留关闭按钮但禁用
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setModal(True)  # 模态对话框

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        self.status_label = QLabel("正在保存数据，请稍候...", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        self.status_label.setFont(font)
        layout.addWidget(self.status_label)

        # 无限循环进度条（表示正在处理）
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)  # 0-0 表示无限循环模式
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

    def set_status(self, text: str):
        """更新状态文字"""
        self.status_label.setText(text)
        # 强制立即重绘，避免卡顿不更新
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
