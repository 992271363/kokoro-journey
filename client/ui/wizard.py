import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox
)
from util.path import _default_appdata, _program_dir
from util.config import Settings


class FirstRunWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 Kokoro Journey")
        self.setFixedSize(520, 240)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        self._selected_path = _default_appdata()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("<b>选择数据存储位置</b>")
        title.setProperty("role", "title")
        layout.addWidget(title)

        desc = QLabel(
            "应用需要创建一个目录来存放本地数据库、设置和未同步数据。\n"
            "你可以使用默认路径，也可以选择放置于根目录或其他位置。"
        )
        desc.setProperty("role", "desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 路径输入行
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self._selected_path)
        self.path_edit.setReadOnly(True)
        path_layout.addWidget(self.path_edit, stretch=1)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # 按钮行
        btn_layout = QHBoxLayout()

        default_btn = QPushButton("默认")
        default_btn.setFixedHeight(34)
        default_btn.setFixedWidth(70)
        default_btn.clicked.connect(self._set_default_dir)
        btn_layout.addWidget(default_btn)

        root_btn = QPushButton("根目录")
        root_btn.setFixedHeight(34)
        root_btn.setFixedWidth(70)
        root_btn.clicked.connect(self._set_root_dir)
        btn_layout.addWidget(root_btn)

        btn_layout.addStretch()

        self.confirm_btn = QPushButton("开始使用")
        self.confirm_btn.setFixedHeight(34)
        self.confirm_btn.setDefault(True)
        self.confirm_btn.clicked.connect(self._confirm)
        btn_layout.addWidget(self.confirm_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setProperty("secondary", True)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "选择数据存储目录",
            self._selected_path,
        )
        if path:
            self._selected_path = path
            self.path_edit.setText(path)

    def _set_root_dir(self):
        self._selected_path = os.path.join(_program_dir(), "data")
        self.path_edit.setText(self._selected_path)

    def _set_default_dir(self):
        self._selected_path = _default_appdata()
        self.path_edit.setText(self._selected_path)

    def _confirm(self):
        path = self._selected_path
        try:
            os.makedirs(path, exist_ok=True)
            # 测试可写性
            test_file = os.path.join(path, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
        except Exception as e:
            QMessageBox.warning(
                self,
                "目录不可用",
                f"无法使用选定的目录：\n{path}\n\n错误：{e}\n\n请选择其他目录。"
            )
            return

        Settings().set("dataDirectory", path)
        self.accept()

    def selected_path(self) -> str:
        return self._selected_path
