from PySide6.QtCore import Qt, QObject, QCollator
from PySide6.QtWidgets import QTableWidgetItem

from util.config import Settings
from ui import table_columns as tc

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
    """集中管理表格排序：方向、冻结(保持顺序)、覆盖键、偏好持久化、表头联动。

    排序键与方向一律以**稳定列 ID** 记录（`tableSortId` / `tableSortOrder`）；
    与表格列号解耦，列隐藏/换序都不会指错。
    """

    def __init__(self, table, manager, settings: Settings = None):
        super().__init__(table)
        self._table = table
        self._manager = manager
        self._settings = settings
        self._preserved = False
        self._preserve_id = "name"
        self._has_override = False
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
        cid = self._manager.col_id(header.sortIndicatorSection())
        order = header.sortIndicatorOrder()
        if cid:
            self._preserve_id = cid
        return cid, order, list(self._manager.row_paths())

    def apply_after_refresh(self, preserve_sort: bool, captured):
        if preserve_sort and captured and captured[0]:
            cid, order, exe_order = captured
            col = self._manager.col_index(cid)
            if 0 <= col < self._table.columnCount():
                index = {exe: i for i, exe in enumerate(exe_order)}
                for r, path in enumerate(self._manager.row_paths()):
                    idx = index.get(path)
                    item = self._table.item(r, col)
                    if item is not None and idx is not None:
                        item.setData(ORDER_OVERRIDE_ROLE, idx)
                SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
                self._table.sortItems(col, order)
                self._table.setSortingEnabled(False)
                self._preserved = True
                self._has_override = True
                return
        self._preserved = False
        self._clear_override_keys()
        self._restore_sort()

    def apply_after_status_update(self):
        if not self._preserved:
            self._clear_override_keys()
            self._ensure_sorting_enabled()

    def unfreeze(self):
        if self._preserved:
            self._preserved = False
            self._clear_override_keys()

    @property
    def preserved(self) -> bool:
        return self._preserved

    def sort_by_id(self, cid: str, order):
        """按稳定 ID 排序并写入偏好（列不可见/未知时忽略）。"""
        col = self._manager.col_index(cid)
        if col < 0:
            return
        if self._settings is not None:
            self._settings.set(tc.SETTING_SORT_ID, cid)
            self._settings.set(tc.SETTING_SORT_ORDER,
                               "asc" if order == Qt.AscendingOrder else "desc")
        SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
        self._table.sortItems(col, order)
        self._ensure_sorting_enabled()

    # ---- 内部 ----
    def _on_indicator_changed(self, column, order):
        SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)

    def _save_preference(self, column, order):
        if not self._settings or getattr(self._manager, "_building_columns", False):
            return
        cid = self._manager.col_id(column)
        if not cid:
            return
        self._settings.set(tc.SETTING_SORT_ID, cid)
        self._settings.set(tc.SETTING_SORT_ORDER,
                           "asc" if order == Qt.AscendingOrder else "desc")

    def resync(self):
        """对齐排序状态：清掉失效指示器，恢复保存的排序，并确保排序开启。

        列显隐/换序/缩放后调用；幂等，可安全重复调用，不会在无变化时反复重排。
        """
        cid = self._settings.get(tc.SETTING_SORT_ID) if self._settings else None
        order_str = self._settings.get(tc.SETTING_SORT_ORDER) if self._settings else None
        col = self._manager.col_index(cid) if cid else -1
        if col >= 0 and order_str in ("asc", "desc"):
            order = Qt.AscendingOrder if order_str == "asc" else Qt.DescendingOrder
            SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
            self._table.sortItems(col, order)
        else:
            self._reset_indicator()
        self._ensure_sorting_enabled()

    def _restore_sort(self):
        self.resync()

    def _ensure_sorting_enabled(self):
        if not self._table.isSortingEnabled():
            self._table.setSortingEnabled(True)

    def _reset_indicator(self):
        """清掉排序指示器（排序列被隐藏/删除后，避免索引残留指向别的列）。"""
        self._table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)

    def _clear_override_keys(self):
        if not self._has_override:
            return
        self._has_override = False
        col = self._manager.col_index(self._preserve_id)
        if col < 0:
            return
        for r in range(self._table.rowCount()):
            item = self._table.item(r, col)
            if item is not None:
                item.setData(ORDER_OVERRIDE_ROLE, None)

    def _on_section_clicked(self, column):
        cid = self._manager.col_id(column)
        if not cid:
            return
        if self._preserved:
            self._preserved = False
            self._clear_override_keys()
            hdr = self._table.horizontalHeader()
            if hdr.sortIndicatorSection() == column:
                new_order = (Qt.DescendingOrder if hdr.sortIndicatorOrder() == Qt.AscendingOrder
                             else Qt.AscendingOrder)
            else:
                new_order = Qt.AscendingOrder
            self.sort_by_id(cid, new_order)
