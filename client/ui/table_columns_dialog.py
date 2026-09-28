"""独立“选择列”弹窗：勾选、调整顺序；确定后一次性应用，取消原样还原。"""
from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from ui import table_columns as tc


class ChooseColumnsDialog(QDialog):
    """列选择：改的是临时状态，点“确定”才应用，取消则丢弃。"""

    def __init__(self, parent, order_ids: List[str], visible_ids: List[str],
                 show_move: bool = True):
        super().__init__(parent)
        self.setWindowTitle("选择列")
        self.resize(420, 520)
        self._visible = set(visible_ids)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾选要显示的列；列表顺序即显示顺序。"))

        self.list = QListWidget()
        layout.addWidget(self.list, stretch=1)

        move_row = QHBoxLayout()
        self.btn_up = QPushButton("上移")
        self.btn_down = QPushButton("下移")
        self.btn_up.clicked.connect(lambda: self._move(-1))
        self.btn_down.clicked.connect(lambda: self._move(1))
        move_row.addWidget(self.btn_up)
        move_row.addWidget(self.btn_down)
        move_row.addStretch()
        layout.addLayout(move_row)
        if not show_move:
            self.btn_up.setVisible(False)
            self.btn_down.setVisible(False)

        btn_reset = QPushButton("恢复默认")
        btn_reset.clicked.connect(self._reset)
        layout.addWidget(btn_reset)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill(tc.sanitize_order(order_ids))

    def _fill(self, order_ids: List[str]):
        self.list.clear()
        for cid in order_ids:
            spec = tc.COLUMNS[cid]
            item = QListWidgetItem(spec.title + ("（预留）" if spec.reserved else ""))
            item.setData(Qt.UserRole, cid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if cid in self._visible else Qt.Unchecked)
            self.list.addItem(item)

    def _move(self, delta: int):
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list.count()):
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def _reset(self):
        self._visible = set(tc.DEFAULT_VISIBLE)
        self._fill(tc.DEFAULT_ORDER)

    def result_state(self) -> Tuple[List[str], List[str]]:
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        visible = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                   if self.list.item(i).checkState() == Qt.Checked]
        return order, visible
