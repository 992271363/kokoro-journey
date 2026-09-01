from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QMessageBox, QDialogButtonBox,
    QInputDialog
)

from db.repository import AppRepository


class GroupDialog(QDialog):
    """分组管理对话框：新建/重命名/删除分组。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("分组管理")
        self.setMinimumSize(360, 400)
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        # 标题
        header = QLabel("<b>分组管理</b>")
        header.setProperty("role", "title")
        layout.addWidget(header)

        # 分组列表
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(16, 16))
        layout.addWidget(self.list_widget)

        # 新建分组
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.new_name_edit = QLineEdit()
        self.new_name_edit.setPlaceholderText("输入新分组名称...")
        self.new_name_edit.setFixedHeight(36)
        add_row.addWidget(self.new_name_edit, stretch=1)

        self.btn_add = QPushButton("新建")
        self.btn_add.setFixedHeight(36)
        self.btn_add.setFixedWidth(80)
        self.btn_add.clicked.connect(self._on_add)
        add_row.addWidget(self.btn_add)
        layout.addLayout(add_row)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_rename = QPushButton("重命名")
        self.btn_rename.setFixedHeight(36)
        self.btn_rename.clicked.connect(self._on_rename)
        btn_row.addWidget(self.btn_rename)

        self.btn_delete = QPushButton("删除")
        self.btn_delete.setFixedHeight(36)
        self.btn_delete.setProperty("danger", True)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)

        layout.addLayout(btn_row)

        # 底部关闭按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        groups = AppRepository.get_all_groups()
        for gid, gname, color in groups:
            item = QListWidgetItem(gname)
            item.setData(Qt.UserRole, gid)
            if color:
                pix = QPixmap(12, 12)
                pix.fill(Qt.transparent)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(color))
                painter.drawEllipse(1, 1, 10, 10)
                painter.end()
                item.setIcon(QIcon(pix))
            self.list_widget.addItem(item)

    def _on_add(self):
        name = self.new_name_edit.text().strip()
        if not name:
            return
        gid = AppRepository.create_group(name)
        if gid is None:
            QMessageBox.warning(self, "提示", f"分组「{name}」已存在。")
        self.new_name_edit.clear()
        self._refresh_list()

    def _on_rename(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        gid = item.data(Qt.UserRole)
        old_name = item.text()

        new_name, ok = QInputDialog.getText(
            self, "重命名分组", "新名称:", text=old_name
        )
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()

        AppRepository.rename_group(gid, new_name)
        self._refresh_list()

    def _on_delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        gid = item.data(Qt.UserRole)
        gname = item.text()

        reply = QMessageBox.question(
            self,
            "删除分组",
            f"确定删除「{gname}」？\n\n分组内的应用不会被删除。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            AppRepository.delete_group(gid)
            self._refresh_list()
