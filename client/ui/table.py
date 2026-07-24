from pathlib import Path
from PySide6.QtCore import Qt, Signal, QObject, QCollator, QSize
from PySide6.QtGui import QFontMetrics, QColor, QPainter, QPainterPath, QPen, QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMenu, QMessageBox, QWidget, QHBoxLayout, QLabel, QApplication
)

from typing import List
from util.format import format_seconds_to_text
from util.icon import get_exe_icon
from db.repository import AppInfo, AppRepository
from util.config import Settings

_collator = QCollator()
_collator.setCaseSensitivity(Qt.CaseInsensitive)

_NOT_RUNNING = -1
_BASE_TOTAL_ROLE = Qt.UserRole + 100
_IS_WATCHED_ROLE = Qt.UserRole + 200
_IS_PATH_EXIST_ROLE = Qt.UserRole + 201
_LAUNCH_PATH_ROLE = Qt.UserRole + 202


class StyledHeaderView(QHeaderView):
    _ARROW_COLOR = QColor(0x47, 0x55, 0x69)
    _DIVIDER_COLOR = QColor(0x94, 0xa3, 0xb8)
    _GRIP_ZONE = 6

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.setMouseTracking(True)
        self._drag_logical = -1

    def _is_on_resizable_edge(self, pos):
        col = self.logicalIndexAt(pos)
        if col < 0:
            return False
        edge_x = self.sectionPosition(col) + self.sectionSize(col)
        return abs(pos.x() - edge_x) <= self._GRIP_ZONE

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)

        if logicalIndex == 2:
            painter.save()
            painter.setPen(QPen(self._DIVIDER_COLOR, 2))
            painter.drawLine(rect.right(), rect.top() + 4, rect.right(), rect.bottom() - 4)
            painter.restore()

        if logicalIndex == self.sortIndicatorSection():
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._ARROW_COLOR)
            order = self.sortIndicatorOrder()
            size = 5
            cx = rect.right() - 14
            cy = rect.center().y()
            if order == Qt.AscendingOrder:
                path = QPainterPath()
                path.moveTo(cx - size, cy + 2)
                path.lineTo(cx + size, cy + 2)
                path.lineTo(cx, cy - size + 2)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                path = QPainterPath()
                path.moveTo(cx - size, cy - 2)
                path.lineTo(cx + size, cy - 2)
                path.lineTo(cx, cy + size - 2)
                path.closeSubpath()
                painter.drawPath(path)
            painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.sectionsMovable():
            self._drag_logical = self.logicalIndexAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_logical >= 0 and (event.buttons() & Qt.LeftButton):
            target = self.logicalIndexAt(event.pos())
            if target >= 0 and target != self._drag_logical:
                self.moveSection(self.visualIndex(self._drag_logical), self.visualIndex(target))
        else:
            if self._is_on_resizable_edge(event.pos()):
                self.setCursor(Qt.SplitHCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_logical = -1
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)


class SortableTableWidgetItem(QTableWidgetItem):
    _ascending = True

    def __lt__(self, other):
        my_val = self.data(Qt.UserRole)
        other_val = other.data(Qt.UserRole)

        if my_val is not None and other_val is not None:
            my_na = (my_val == _NOT_RUNNING)
            other_na = (other_val == _NOT_RUNNING)
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
        return _collator.compare(self.text(), other.text()) < 0


class AppTableManager(QObject):
    detail_requested = Signal(str)
    launch_requested = Signal(str)
    watch_toggled_requested = Signal(str, bool)
    hard_delete_requested = Signal(str, str)
    table_width_hint = Signal(int)

    def __init__(self, table_widget: QTableWidget, parent=None, settings: Settings = None):
        super().__init__(parent)
        self.table = table_widget
        self._settings = settings
        self._zoom_factor = 1.0
        self._base_font = QFont(self.table.font())
        self._last_apps: List[AppInfo] = []
        self._setup_table()

    def apply_zoom(self, factor: float, live_preview: bool = False):
        factor = max(0.5, min(2.5, factor))
        self._zoom_factor = factor

        font = QFont(self._base_font)
        base_size = self._base_font.pointSizeF() or 13
        font.setPointSizeF(base_size * factor)
        self.table.setFont(font)
        self.table.horizontalHeader().setFont(font)

        row_h = QFontMetrics(font).height() + 12
        icon_sz = max(8, int(round(20 * factor)))
        icon_sz = min(icon_sz, row_h - 4)
        self.table.setIconSize(QSize(icon_sz, icon_sz))

        self.table.setColumnWidth(2, max(50, int(round(250 * factor))))

        if self._last_apps:
            self.refresh(self._last_apps, skip_width_hint=True)

    def _setup_table(self):
        columns = ["状态", "", "应用名称", "本次焦点", "本次运行", "最后一次启动", "首次启动", "总焦点时长", "总运行时长"]
        self.table.setColumnCount(len(columns))

        header = StyledHeaderView(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        self.table.setHorizontalHeaderLabels(columns)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setColumnWidth(2, 250)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(20, 20))

        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._save_sort_preference)

        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.sectionMoved.connect(self._save_column_order)
        self._restore_column_order()

    def _create_status_icon(self, color_hex: str) -> QIcon:
        canvas = max(self.table.iconSize().width(), 8)
        dot = min(canvas, 24)
        pixmap = QPixmap(canvas, canvas)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.NoPen)
        x = (canvas - dot) // 2
        y = (canvas - dot) // 2
        painter.drawEllipse(x, y, dot, dot)
        painter.end()
        return QIcon(pixmap)

    def refresh(self, apps: List[AppInfo], skip_width_hint: bool = False):
        self._last_apps = apps
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for app in apps:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # 状态列：根据 is_watched / is_path_exist 决定颜色
            if not app.is_path_exist:
                status_color = "#ef4444"
                status_text = "路径不存在"
                status_value = -2
            elif not app.is_watched:
                status_color = "#334155"
                status_text = "未监视"
                status_value = -1
            else:
                status_color = "#cbd5e0"
                status_text = "未运行"
                status_value = 0

            status_item = SortableTableWidgetItem("")
            status_item.setData(Qt.UserRole, status_value)
            status_item.setIcon(self._create_status_icon(status_color))
            status_item.setToolTip(status_text)
            self.table.setItem(row, 0, status_item)

            # 图标列
            icon_item = SortableTableWidgetItem("")
            icon_item.setIcon(get_exe_icon(app.exe_path))
            self.table.setItem(row, 1, icon_item)

            name_item = SortableTableWidgetItem(Path(app.exe_name).stem)
            name_item.setData(Qt.UserRole, app.exe_path)
            name_item.setData(_LAUNCH_PATH_ROLE, app.launch_path or app.exe_path)
            name_item.setData(_IS_WATCHED_ROLE, app.is_watched)
            name_item.setData(_IS_PATH_EXIST_ROLE, app.is_path_exist)
            # 显示颜色标记
            if app.color_tags:
                dots = " ".join(f'<span style="color:{c};">●</span>' for c in app.color_tags)
                name_item.setText(f"{Path(app.exe_name).stem}  {dots}")
            self.table.setItem(row, 2, name_item)

            item_cur_focus = SortableTableWidgetItem("-")
            item_cur_focus.setData(Qt.UserRole, _NOT_RUNNING)
            self.table.setItem(row, 3, item_cur_focus)

            item_cur_run = SortableTableWidgetItem("-")
            item_cur_run.setData(Qt.UserRole, _NOT_RUNNING)
            self.table.setItem(row, 4, item_cur_run)

            item_last_start = SortableTableWidgetItem(app.last_start_at)
            item_last_start.setData(Qt.UserRole, app.last_start_at_ts or 0)
            self.table.setItem(row, 5, item_last_start)

            item_first_seen = SortableTableWidgetItem(app.first_seen_at)
            item_first_seen.setData(Qt.UserRole, app.first_seen_at_ts or 0)
            self.table.setItem(row, 6, item_first_seen)

            item_focus = SortableTableWidgetItem(format_seconds_to_text(app.total_focus_seconds))
            item_focus.setData(Qt.UserRole, app.total_focus_seconds)
            item_focus.setData(_BASE_TOTAL_ROLE, app.total_focus_seconds)
            self.table.setItem(row, 7, item_focus)

            item_life = SortableTableWidgetItem(format_seconds_to_text(app.total_lifetime_seconds))
            item_life.setData(Qt.UserRole, app.total_lifetime_seconds)
            item_life.setData(_BASE_TOTAL_ROLE, app.total_lifetime_seconds)
            self.table.setItem(row, 8, item_life)

        self._restore_sort()
        self._adjust_name_column_width()
        if not skip_width_hint:
            self._emit_table_width_hint()

    def update_status(self, status_data: dict):
        self.table.setSortingEnabled(False)
        for row in range(self.table.rowCount()):
            exe_name_item = self.table.item(row, 2)
            if not exe_name_item:
                continue

            is_path_exist = exe_name_item.data(_IS_PATH_EXIST_ROLE)
            is_watched = exe_name_item.data(_IS_WATCHED_ROLE)

            # 路径不存在：保持红色，跳过
            if is_path_exist is False:
                status_item = self.table.item(row, 0)
                if status_item:
                    status_item.setIcon(self._create_status_icon("#ef4444"))
                    status_item.setToolTip("路径不存在")
                continue

            # 未监视：保持深灰，跳过
            if is_watched is False:
                status_item = self.table.item(row, 0)
                if status_item:
                    status_item.setData(Qt.UserRole, -1)
                    status_item.setIcon(self._create_status_icon("#334155"))
                    status_item.setToolTip("未监视")
                item_cur_focus = SortableTableWidgetItem("-")
                item_cur_focus.setData(Qt.UserRole, _NOT_RUNNING)
                self.table.setItem(row, 3, item_cur_focus)
                item_cur_run = SortableTableWidgetItem("-")
                item_cur_run.setData(Qt.UserRole, _NOT_RUNNING)
                self.table.setItem(row, 4, item_cur_run)
                continue

            exe_path = exe_name_item.data(Qt.UserRole)

            item_total_focus = self.table.item(row, 7)
            item_total_life = self.table.item(row, 8)
            if not item_total_focus or not item_total_life:
                continue

            base_focus = item_total_focus.data(_BASE_TOTAL_ROLE)
            base_life = item_total_life.data(_BASE_TOTAL_ROLE)

            if base_focus is None:
                base_focus = item_total_focus.data(Qt.UserRole) or 0
            if base_life is None:
                base_life = item_total_life.data(Qt.UserRole) or 0

            if exe_path in status_data:
                data = status_data[exe_path]
                status_color = "#48bb78" if data['is_focused'] else "#4299e1"
                status_val = 2 if data['is_focused'] else 1

                status_item = self.table.item(row, 0)
                if status_item:
                    status_item.setData(Qt.UserRole, status_val)
                    status_item.setIcon(self._create_status_icon(status_color))

                item_cur_focus = SortableTableWidgetItem(format_seconds_to_text(data['focus']))
                item_cur_focus.setData(Qt.UserRole, data['focus'])
                self.table.setItem(row, 3, item_cur_focus)

                item_cur_run = SortableTableWidgetItem(format_seconds_to_text(data['runtime_seconds']))
                item_cur_run.setData(Qt.UserRole, data['runtime_seconds'])
                self.table.setItem(row, 4, item_cur_run)

                current_total_focus = base_focus + data['focus']
                item_total_focus.setText(format_seconds_to_text(current_total_focus))
                item_total_focus.setData(Qt.UserRole, current_total_focus)

                current_total_life = base_life + data['runtime_seconds']
                item_total_life.setText(format_seconds_to_text(current_total_life))
                item_total_life.setData(Qt.UserRole, current_total_life)
            else:
                status_item = self.table.item(row, 0)
                if status_item and status_item.data(Qt.UserRole) > 0:
                    final_focus = item_total_focus.data(Qt.UserRole)
                    final_life = item_total_life.data(Qt.UserRole)

                    if final_focus is not None:
                        item_total_focus.setData(_BASE_TOTAL_ROLE, final_focus)
                    if final_life is not None:
                        item_total_life.setData(_BASE_TOTAL_ROLE, final_life)

                    status_item.setData(Qt.UserRole, 0)
                    status_item.setIcon(self._create_status_icon("#cbd5e0"))

                    item_cur_focus = SortableTableWidgetItem("-")
                    item_cur_focus.setData(Qt.UserRole, _NOT_RUNNING)
                    self.table.setItem(row, 3, item_cur_focus)

                    item_cur_run = SortableTableWidgetItem("-")
                    item_cur_run.setData(Qt.UserRole, _NOT_RUNNING)
                    self.table.setItem(row, 4, item_cur_run)

                    final_focus = item_total_focus.data(_BASE_TOTAL_ROLE) or base_focus
                    final_life = item_total_life.data(_BASE_TOTAL_ROLE) or base_life

                    item_total_focus.setText(format_seconds_to_text(final_focus))
                    item_total_life.setText(format_seconds_to_text(final_life))
                    item_total_focus.setData(Qt.UserRole, final_focus)
                    item_total_life.setData(Qt.UserRole, final_life)
        self.table.setSortingEnabled(True)

    def set_row_watched_state(self, exe_path: str, watched: bool):
        """只更新指定行的监视状态，不重建整张表。"""
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)
            if not name_item or name_item.data(Qt.UserRole) != exe_path:
                continue

            name_item.setData(_IS_WATCHED_ROLE, watched)

            if not watched:
                status_item = self.table.item(row, 0)
                if status_item:
                    status_item.setData(Qt.UserRole, -1)
                    status_item.setIcon(self._create_status_icon("#334155"))
                    status_item.setToolTip("未监视")
                item_cur_focus = SortableTableWidgetItem("-")
                item_cur_focus.setData(Qt.UserRole, _NOT_RUNNING)
                self.table.setItem(row, 3, item_cur_focus)
                item_cur_run = SortableTableWidgetItem("-")
                item_cur_run.setData(Qt.UserRole, _NOT_RUNNING)
                self.table.setItem(row, 4, item_cur_run)
            else:
                status_item = self.table.item(row, 0)
                if status_item:
                    status_item.setData(Qt.UserRole, 0)
                    status_item.setIcon(self._create_status_icon("#cbd5e0"))
                    status_item.setToolTip("未运行")
            break

    def _on_double_clicked(self, index):
        row = index.row()
        exe_path = self._get_exe_path_by_row(row)
        if exe_path:
            self.detail_requested.emit(exe_path)

    def _on_context_menu(self, pos):
        row = self.table.currentRow()
        if row < 0:
            return

        name_item = self.table.item(row, 2)
        if not name_item:
            return

        exe_name = name_item.text()
        exe_path = name_item.data(Qt.UserRole)
        is_watched = bool(name_item.data(_IS_WATCHED_ROLE))

        menu = QMenu()
        detail_action = menu.addAction("查看详细信息")
        launch_action = menu.addAction("启动此应用")
        menu.addSeparator()
        toggle_watch_action = menu.addAction("停止监视" if is_watched else "恢复监视")

        # 分组子菜单
        group_menu = menu.addMenu("分组")
        manage_groups_action = group_menu.addAction("管理分组...")
        group_menu.addSeparator()
        all_groups = AppRepository.get_all_groups()
        current_groups = [gid for gid, _ in AppRepository.get_app_groups(exe_path)]
        group_actions = {}
        for gid, gname in all_groups:
            act = group_menu.addAction(gname)
            act.setCheckable(True)
            act.setChecked(gid in current_groups)
            group_actions[act] = gid

        # 颜色标记子菜单
        color_menu = menu.addMenu("标记")
        COLORS = [
            ("#60a5fa", "蓝色"),
            ("#34d399", "绿色"),
            ("#f87171", "红色"),
            ("#fb923c", "橙色"),
            ("#a78bfa", "紫色"),
            ("#facc15", "黄色"),
        ]
        current_colors = AppRepository.get_color_tags(exe_path)
        color_actions = {}
        for hex_val, label in COLORS:
            act = color_menu.addAction(f"  {label}")
            act.setCheckable(True)
            act.setChecked(hex_val in current_colors)
            color_actions[act] = hex_val
        color_menu.addSeparator()
        clear_colors_action = color_menu.addAction("清除所有标记")

        menu.addSeparator()
        hard_delete_action = menu.addAction("彻底删除此应用...")

        action = menu.exec(self.table.mapToGlobal(pos))

        if action == detail_action:
            self.detail_requested.emit(exe_path)
        elif action == launch_action:
            launch_path = name_item.data(_LAUNCH_PATH_ROLE) or exe_path
            self.launch_requested.emit(launch_path)
        elif action == toggle_watch_action:
            self.watch_toggled_requested.emit(exe_path, not is_watched)
        elif action == manage_groups_action:
            from ui.group import GroupDialog
            GroupDialog(self.table).exec()
        elif action == clear_colors_action:
            AppRepository.clear_color_tags(exe_path)
            self._refresh_color_dots(row, exe_path)
        elif action in group_actions:
            gid = group_actions[action]
            AppRepository.toggle_app_group(exe_path, gid)
        elif action in color_actions:
            color = color_actions[action]
            if color in current_colors:
                AppRepository.remove_color_tag(exe_path, color)
            else:
                AppRepository.add_color_tag(exe_path, color)
            self._refresh_color_dots(row, exe_path)
        elif action == hard_delete_action:
            if self._confirm_hard_delete(exe_name):
                self.hard_delete_requested.emit(exe_path, exe_name)

    def _refresh_color_dots(self, row: int, exe_path: str):
        """更新名称列的颜色圆点。"""
        name_item = self.table.item(row, 2)
        if not name_item:
            return
        base_name = Path(name_item.text()).stem if Path(name_item.text()).suffix else name_item.text()
        tags = AppRepository.get_color_tags(exe_path)
        if tags:
            dots = " ".join(f'<span style="color:{c};">●</span>' for c in tags)
            name_item.setText(f"{base_name}  {dots}")
        else:
            name_item.setText(base_name)

    def _confirm_hard_delete(self, exe_name: str) -> bool:
        first = QMessageBox.warning(
            self.table,
            "删除应用",
            f"确定要彻底删除「{exe_name}」吗？\n\n"
            "这会删除该应用的历史统计、会话记录和焦点记录。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if first != QMessageBox.Yes:
            return False

        second = QMessageBox.critical(
            self.table,
            "再次确认",
            f"此操作不可恢复。\n\n"
            f"是否确认永久删除「{exe_name}」的所有数据？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return second == QMessageBox.Yes

    def _get_exe_path_by_row(self, row: int) -> str:
        item = self.table.item(row, 2)
        if item:
            return item.data(Qt.UserRole)
        return ""

    def _on_sort_indicator_changed(self, column, order):
        SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)

    def _save_sort_preference(self, column: int, order):
        if not self._settings:
            return
        self._settings.set("tableSortColumn", column)
        self._settings.set("tableSortOrder", "asc" if order == Qt.AscendingOrder else "desc")

    def _restore_sort(self):
        if not self._settings:
            self.table.setSortingEnabled(True)
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
                if 0 <= col < self.table.columnCount():
                    order = Qt.AscendingOrder if order_str == "asc" else Qt.DescendingOrder
                    SortableTableWidgetItem._ascending = (order == Qt.AscendingOrder)
                    self.table.sortItems(col, order)
            except (TypeError, ValueError):
                pass
        self.table.setSortingEnabled(True)

    def _adjust_name_column_width(self):
        name_col = 2

        cell_fm = QFontMetrics(self.table.font())
        header_fm = QFontMetrics(self.table.horizontalHeader().font())

        header_item = self.table.horizontalHeaderItem(name_col)
        header_text = header_item.text() if header_item else "应用名称"

        header_text_width = header_fm.horizontalAdvance(header_text)
        header_min_width = header_text_width + int(round(60 * self._zoom_factor))

        max_content_width = 0

        for row in range(self.table.rowCount()):
            item = self.table.item(row, name_col)
            if item:
                text_width = cell_fm.horizontalAdvance(item.text())
                max_content_width = max(max_content_width, text_width)

        content_width = max_content_width + int(round(40 * self._zoom_factor))

        final_width = max(header_min_width, content_width)

        self.table.setColumnWidth(name_col, final_width)

    def _emit_table_width_hint(self):   
        total = 0
        for col in range(self.table.columnCount()):
            total += self.table.columnWidth(col)
        if self.table.verticalScrollBar().isVisible():
            total += self.table.verticalScrollBar().width()
        self.table_width_hint.emit(total + int(round(90 * self._zoom_factor)))

    def _save_column_order(self):
        if not self._settings:
            return
        header = self.table.horizontalHeader()
        order = [header.logicalIndex(v) for v in range(header.count())]
        self._settings.set("tableColumnOrder", order)

    def _restore_column_order(self):
        if not self._settings:
            return
        order = self._settings.get("tableColumnOrder")
        if not order or len(order) != self.table.columnCount():
            return
        header = self.table.horizontalHeader()
        for visual_idx, logical_idx in enumerate(order):
            if 0 <= logical_idx < header.count():
                header.moveSection(header.visualIndex(logical_idx), visual_idx)
