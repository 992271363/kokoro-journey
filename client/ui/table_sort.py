from PySide6.QtCore import Qt, QObject, QCollator
from PySide6.QtWidgets import QTableWidgetItem

from util.config import Settings

collator = QCollator()
collator.setCaseSensitivity(Qt.CaseInsensitive)

NOT_RUNNING = -1
ORDER_OVERRIDE_ROLE = Qt.UserRole + 500


class SortableTableWidgetItem(QTableWidgetItem):
    _ascending = True

    def __lt__(self, other):
        my_order = self.data(ORDER_OVERRIDE_ROLE)
        other_order = other.data(ORDER_OVERRIDE_ROLE)
        if my_order is not None and other_order is not None:
            if SortableTableWidgetItem._ascending:
                return my_order < other_order
            return my_order > other_order

        my_val = self.data(Qt.UserRole)
        other_val = other.data(Qt.UserRole)

        if my_val is not None and other_val is not None:
            my_na = (my_val == NOT_RUNNING)
            other_na = (other_val == NOT_RUNNING)
            if my_na != other_na:
                if my_na:
                    return not SortableTableWidgetItem._ascending
                return SortableTableWidgetItem._ascending
            if my_na and other_na:
                return False
            try:
                return float(my_val) < float(other_val)
            except (TypeError, ValueError):
                pass
        return collator.compare(self.text(), other.text()) < 0


class SortController(QObject):
    """集中管理表格排序：方向、冻结(保持顺序)、覆盖键、偏好持久化、表头联动。"""

    def __init__(self, table, settings: Settings = None):
        super().__init__(table)
        self._table = table
        self._settings = settings
        self._preserved = False
        self._preserve_col = 2
        self._wire_header()

    # ---- 表头联动 ----
    def _wire_header(self):
        self._table.setSortingEnabled(True)
        header = self._table.horizontalHeader()
        header.sortIndicatorChanged.connect(self._on_indicator_changed)
        header.sortIndicatorChanged.connect(self._save_preference)
        header.sectionClicked.connect(self._on_section_clicked)

    # ---- 对外 API ----
    def begin_refresh(self):
        self._table.setSortingEnabled(False)

    def capture_order(self):
        header = self._table.horizontalHeader()
        col = header.sortIndicatorSection()
        order = header.sortIndicatorOrder()
        self._preserve_col = col
        exe_order = []
        for r in range(self._table.rowCount()):
            ni = self._table.item(r, 2)
            if ni:
                exe_order.append(ni.data(Qt.UserRole))
        return col, order, exe_order

    def apply_after_refresh(self, preserve_sort: bool, captured):
        if preserve_sort:
            col, order, exe_order = captured
            index = {exe: i for i, exe in enumerate(exe_order)}
            for r in range(self._table.rowCount()):
                ni = self._table.item(r, 2)
                if not ni:
                    continue
                idx = index.get(ni.data(Qt.UserRole))
                if idx is not None:
                    si = self._table.item(r, col)
                    if si:
                        si.setData(ORDER_OVERRIDE_ROLE, idx)
            SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
            self._table.sortItems(col, order)
            self._table.setSortingEnabled(False)
            self._preserved = True
        else:
            self._preserved = False
            self._clear_override_keys()
            self._restore_sort()

    def apply_after_status_update(self):
        if not self._preserved:
            self._clear_override_keys()
            self._table.setSortingEnabled(True)

    def unfreeze(self):
        if self._preserved:
            self._preserved = False
            self._clear_override_keys()

    @property
    def preserved(self) -> bool:
        return self._preserved

    # ---- 内部 ----
    def _on_indicator_changed(self, column, order):
        SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)

    def _save_preference(self, column: int, order):
        if not self._settings:
            return
        self._settings.set("tableSortColumn", column)
        self._settings.set("tableSortOrder", "asc" if order == Qt.AscendingOrder else "desc")

    def _restore_sort(self):
        if not self._settings:
            self._table.setSortingEnabled(True)
            return
        col = self._settings.get("tableSortColumn")
        order_str = self._settings.get("tableSortOrder")
        if col is not None and order_str is not None:
            try:
                col = int(col)
                # 列迁移：图标列插入后，旧排序列 >= 1 的索引 +1（仅一次）
                if col >= 1 and not self._settings.get("_col_migrated"):
                    col += 1
                    self._settings.set("tableSortColumn", col)
                    self._settings.set("_col_migrated", True)
                if 0 <= col < self._table.columnCount():
                    order = Qt.AscendingOrder if order_str == "asc" else Qt.DescendingOrder
                    SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
                    self._table.sortItems(col, order)
            except (TypeError, ValueError):
                pass
        self._table.setSortingEnabled(True)

    def _clear_override_keys(self):
        for r in range(self._table.rowCount()):
            si = self._table.item(r, self._preserve_col)
            if si:
                si.setData(ORDER_OVERRIDE_ROLE, None)

    def _on_section_clicked(self, column):
        if self._preserved:
            self._preserved = False
            self._clear_override_keys()
            hdr = self._table.horizontalHeader()
            if hdr.sortIndicatorSection() == column:
                new_order = Qt.DescendingOrder if hdr.sortIndicatorOrder() == Qt.AscendingOrder else Qt.AscendingOrder
            else:
                new_order = Qt.AscendingOrder
            self._table.setSortingEnabled(True)
            self._table.sortByColumn(column, new_order)
