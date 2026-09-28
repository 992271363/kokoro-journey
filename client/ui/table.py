from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QObject, QSize
from PySide6.QtGui import QFontMetrics, QColor, QPainter, QPainterPath, QPen, QFont, QPixmap, QIcon, QShortcut, QAction
from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMenu, QMessageBox, QStyledItemDelegate, QLineEdit, QApplication
)

from typing import Dict, List, Optional
from util.format import format_seconds_to_text
from util.icon import get_exe_icon
from db.repository import AppInfo, AppRepository
from util.config import Settings
from ui import table_columns as tc
from ui.table_sort import SortableTableWidgetItem, SortController, NOT_RUNNING as _NOT_RUNNING


@dataclass
class RowState:
    """一行的数据与实时状态。

    不依赖任何单元格：列被隐藏/换序时，基准值与实时值都不会丢。
    """
    app: AppInfo
    status_value: int = 0
    status_text: str = "未运行"
    base_focus: int = 0
    base_lifetime: int = 0
    session_focus: int = -1     # -1 = 未运行
    session_lifetime: int = -1
    running: bool = False
    focused: bool = False


def should_offer_le_launch(launch_with_le: bool) -> bool:
    """已勾选“用 Locale Emulator 启动”的应用，不再单独提供一次性 LE 入口。"""
    return not bool(launch_with_le)

# 每个单元格都记录所属行的 exe_path：排序/换序后单元格随行移动，
# 行身份始终按“视觉行”解析，避免用数据下标写错行。
EXE_PATH_ROLE = Qt.UserRole + 510

_LIGHT_STATUS_COLORS = {
    "path_missing": "#ef4444",
    "not_watched": "#94a3b8",
    "not_running": "#cbd5e1",
    "focused": "#22c55e",
    "running": "#3b82f6",
}

_STATUS_VALUE_TO_KEY = {1: "running", 2: "focused", 0: "not_running", -1: "not_watched", -2: "path_missing"}
_DARK_STATUS_COLORS = {
    "path_missing": "#ef4444",
    "not_watched": "#64748b",
    "not_running": "#475569",
    "focused": "#22c55e",
    "running": "#3b82f6",
}


class StyledHeaderView(QHeaderView):
    _GRIP_ZONE = 6

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.setMouseTracking(True)
        self._drag_logical = -1
        self._arrow_color = QColor(0x47, 0x55, 0x69)
        self._divider_color = QColor(0x94, 0xa3, 0xb8)
        self._name_col = 2       # 名称列位置（随列配置变化，由表格更新）

    def set_name_column(self, index: int):
        self._name_col = index
        self.viewport().update()

    def set_dark_mode(self, is_dark: bool):
        if is_dark:
            self._arrow_color = QColor(0x94, 0xa3, 0xb8)
            self._divider_color = QColor(0x47, 0x55, 0x69)
        else:
            self._arrow_color = QColor(0x47, 0x55, 0x69)
            self._divider_color = QColor(0x94, 0xa3, 0xb8)
        self.viewport().update()

    def _is_on_resizable_edge(self, pos):
        col = self.logicalIndexAt(pos)
        if col < 0:
            return False
        edge_x = self.sectionPosition(col) + self.sectionSize(col)
        return abs(pos.x() - edge_x) <= self._GRIP_ZONE

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)

        if logicalIndex == self._name_col:
            painter.save()
            painter.setPen(QPen(self._divider_color, 2))
            painter.drawLine(rect.right(), rect.top() + 4, rect.right(), rect.bottom() - 4)
            painter.restore()

        if logicalIndex == self.sortIndicatorSection():
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._arrow_color)
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


class AppTableManager(QObject):
    detail_requested = Signal(str)
    launch_requested = Signal(str, bool)  # (exe_path, 本次是否强制走 Locale Emulator)
    watch_toggled_requested = Signal(str, bool)
    hard_delete_requested = Signal(str, str)
    table_width_hint = Signal(int)
    columns_changed = Signal()            # 列显隐/顺序变化后发出（供搜索等重新应用）

    def __init__(self, table_widget: QTableWidget, parent=None, settings: Settings = None):
        super().__init__(parent)
        self.table = table_widget
        self._settings = settings
        self._zoom_factor = 1.0
        self._base_font = QFont(self.table.font())
        self._last_apps: List[AppInfo] = []
        self._rows: Dict[str, RowState] = {}     # exe_path -> RowState
        self._row_paths: List[str] = []          # 行顺序（行号 -> exe_path）
        self._group_names: Dict[int, str] = {}   # 分组 id -> 名称
        self._is_dark = False
        self._status_colors = dict(_LIGHT_STATUS_COLORS)
        self._header = None
        self._editing_rename = False
        self._rename_row = -1
        self._rename_exe_path = ""
        self._rename_original = ""
        self._restore_edit_triggers = QAbstractItemView.EditTrigger.NoEditTriggers
        self._rename_editor_widget = None
        self._building_columns = False

        # 列偏好（含旧的“按列号”偏好一次性迁移）
        tc.migrate_legacy_prefs(self._settings)
        self._order_ids = tc.load_order(self._settings)
        self._visible_ids = tc.load_visible(self._settings, self._order_ids)

        self._setup_table()
        self._sort = SortController(self.table, self, self._settings)

    def set_dark_mode(self, is_dark: bool):
        self._is_dark = is_dark
        self._status_colors = dict(_DARK_STATUS_COLORS if is_dark else _LIGHT_STATUS_COLORS)
        if self._header:
            self._header.set_dark_mode(is_dark)
        self._repaint_status_icons()
        self.reassert_zoom()

    def _repaint_status_icons(self):
        col = self.col_index("status")
        if col < 0:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, col)
            if item is None:
                continue
            value = item.data(Qt.UserRole)
            key = _STATUS_VALUE_TO_KEY.get(value)
            if key and key in self._status_colors:
                item.setIcon(self._create_status_icon(self._status_colors[key]))

    def apply_zoom(self, factor: float):
        factor = max(0.5, min(2.5, factor))
        if factor != self._zoom_factor:
            self._zoom_factor = factor
        self._apply_zoom_style()

        if self._last_apps:
            # 只重绘单元格，保留 _rows 中的实时会话状态；
            # _render_rows 内部会关闭排序，渲染后按原状态恢复排序与指示器
            was_sorting = self.table.isSortingEnabled()
            self._render_rows()
            self._adjust_name_column_width()
            if was_sorting:
                self._sort.resync()

    def _apply_zoom_style(self):
        font = QFont(self._base_font)
        pt = self._base_font.pointSizeF()
        px = self._base_font.pixelSize()
        factor = self._zoom_factor
        if pt > 0:
            font.setPointSizeF(pt * factor)
        else:
            base_pt = (px if px > 0 else 13) * 72.0 / 96.0
            font.setPointSizeF(base_pt * factor)
        self.table.setFont(font)
        self.table.horizontalHeader().setFont(font)

        row_h = QFontMetrics(font).height() + 12
        icon_sz = max(8, int(round(20 * factor)))
        icon_sz = min(icon_sz, row_h - 4)
        self.table.setIconSize(QSize(icon_sz, icon_sz))

        name_col = self.col_index("name")
        if name_col >= 0:
            self.table.setColumnWidth(name_col, max(50, int(round(250 * factor))))

    def reassert_zoom(self):
        self._apply_zoom_style()
        self._adjust_name_column_width()

    def _setup_table(self):
        header = StyledHeaderView(Qt.Horizontal, self.table)
        self._header = header
        self.table.setHorizontalHeader(header)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSectionsMovable(True)
        header.setDragEnabled(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_menu)
        header.sectionMoved.connect(self._on_section_moved)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(20, 20))

        f2_shortcut = QShortcut(Qt.Key_F2, self.table)
        f2_shortcut.activated.connect(self._on_f2_press)

        self._apply_columns_config()

    # ---------- 列（按稳定 ID） ----------

    @property
    def visible_ids(self) -> List[str]:
        return list(self._visible_ids)

    @property
    def order_ids(self) -> List[str]:
        return list(self._order_ids)

    def col_index(self, cid: Optional[str]) -> int:
        """稳定 ID → 当前表格列号（不可见返回 -1）。"""
        if not cid:
            return -1
        try:
            return self._visible_ids.index(cid)
        except ValueError:
            return -1

    def col_id(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._visible_ids):
            return self._visible_ids[index]
        return None

    def row_paths(self) -> List[str]:
        return list(self._row_paths)

    def _apply_columns_config(self):
        """按当前 order/visible 重建列，并重绘所有行。"""
        self._building_columns = True
        self.table.setSortingEnabled(False)
        cols = list(self._visible_ids)
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels([tc.COLUMNS[cid].header_text() for cid in cols])

        header = self.table.horizontalHeader()
        mode_map = {
            "interactive": QHeaderView.Interactive,
            "fixed": QHeaderView.Fixed,
            "contents": QHeaderView.ResizeToContents,
        }
        for c, cid in enumerate(cols):
            spec = tc.COLUMNS[cid]
            header.setSectionResizeMode(c, mode_map.get(spec.resize, QHeaderView.ResizeToContents))
            self.table.setColumnWidth(c, spec.width)

        # 名称列分隔线 + 内联编辑委托
        name_col = self.col_index("name")
        if self._header is not None:
            self._header.set_name_column(name_col)
        self._name_delegate = _NameEditorDelegate(self.table)
        if name_col >= 0:
            self.table.setItemDelegateForColumn(name_col, self._name_delegate)

        status_col = self.col_index("status")
        if status_col >= 0:
            item = self.table.horizontalHeaderItem(status_col)
            if item is not None:
                item.setToolTip("状态：未运行 / 未监视 / 路径不存在")

        self._building_columns = False
        self._render_rows()
        if self.col_index("name") >= 0:
            self._adjust_name_column_width()

    def set_column_visible(self, cid: str, visible: bool):
        if not tc.is_known(cid):
            return
        if visible and cid not in self._visible_ids:
            # 按 order 的位置插入，而不是追加到末尾，保证列序稳定
            self._visible_ids = tc.sanitize_visible(self._visible_ids + [cid], self._order_ids)
        elif not visible and cid in self._visible_ids:
            self._visible_ids.remove(cid)
            if cid == self._sort_id():
                self._clear_sort()
        else:
            return
        self._persist_columns()
        self._apply_columns_config()
        self._sort.resync()
        self.columns_changed.emit()

    def set_columns(self, order_ids, visible_ids):
        self._order_ids = tc.sanitize_order(order_ids)
        self._visible_ids = tc.sanitize_visible(visible_ids, self._order_ids)
        if self._sort_id() and self._sort_id() not in self._visible_ids:
            self._clear_sort()
        self._persist_columns()
        self._apply_columns_config()
        self._sort.resync()
        self.columns_changed.emit()

    def reset_columns(self):
        self.set_columns(tc.DEFAULT_ORDER, tc.DEFAULT_VISIBLE)

    def _persist_columns(self):
        if self._settings is None:
            return
        self._settings.set(tc.SETTING_ORDER, self._order_ids)
        self._settings.set(tc.SETTING_VISIBLE, self._visible_ids)

    def _sort_id(self) -> Optional[str]:
        return self._settings.get(tc.SETTING_SORT_ID) if self._settings is not None else None

    def _clear_sort(self):
        if self._settings is not None:
            self._settings.set(tc.SETTING_SORT_ID, None)
            self._settings.set(tc.SETTING_SORT_ORDER, None)

    def sort_by_id(self, cid: str, order):
        self._sort.sort_by_id(cid, order)

    def _on_section_moved(self, logical, old_visual, new_visual):
        """表头拖拽调序：把视觉顺序换算回 ID 顺序并保存（不重建列）。"""
        if self._building_columns:
            return
        header = self.table.horizontalHeader()
        cols = list(self._visible_ids)
        try:
            new_visible = [cols[header.logicalIndex(v)] for v in range(header.count())]
        except (IndexError, KeyError):
            return
        visible_set = set(cols)
        it = iter(new_visible)
        self._order_ids = [next(it) if cid in visible_set else cid for cid in self._order_ids]
        self._visible_ids = tc.sanitize_visible(self._visible_ids, self._order_ids)
        self._persist_columns()

    # ---------- 表头右键（即时生效） ----------

    def _on_header_menu(self, pos):
        header = self.table.horizontalHeader()
        logical = header.logicalIndexAt(pos)
        cid = self.col_id(logical) if logical >= 0 else None

        menu = QMenu(self.table)
        menu.addAction("显示的列").setEnabled(False)
        for column_id in self._order_ids:
            spec = tc.COLUMNS[column_id]
            act = QAction(spec.title + ("（预留）" if spec.reserved else ""), menu)
            act.setCheckable(True)
            act.setChecked(column_id in self._visible_ids)
            act.toggled.connect(
                lambda on, c=column_id: self.set_column_visible(c, on))
            menu.addAction(act)

        if cid is not None:
            spec = tc.COLUMNS[cid]
            menu.addSeparator()
            if not spec.sortable:
                # 不可排序列：先按“显示但禁用”呈现（最终规则后续再定）
                act = QAction(f"按「{spec.title}」排序（不可用）", menu)
                act.setEnabled(False)
                act.setToolTip("该列没有可比较的取值")
                menu.addAction(act)
            else:
                act_asc = QAction(f"按「{spec.title}」升序", menu)
                act_desc = QAction(f"按「{spec.title}」降序", menu)
                act_asc.triggered.connect(
                    lambda _c=False, c=cid: self.sort_by_id(c, Qt.AscendingOrder))
                act_desc.triggered.connect(
                    lambda _c=False, c=cid: self.sort_by_id(c, Qt.DescendingOrder))
                menu.addAction(act_asc)
                menu.addAction(act_desc)

        menu.addSeparator()
        act_more = QAction("更多…（选择列）", menu)
        act_more.triggered.connect(self.open_choose_columns)
        menu.addAction(act_more)
        menu.exec(header.mapToGlobal(pos))

    def open_choose_columns(self):
        from ui.table_columns_dialog import ChooseColumnsDialog
        dialog = ChooseColumnsDialog(self.table, self._order_ids, self._visible_ids)
        if dialog.exec() == dialog.Accepted:
            order, visible = dialog.result_state()
            self.set_columns(order, visible)

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

    def refresh(self, apps: List[AppInfo], skip_width_hint: bool = False, preserve_sort: bool = False):
        self._set_data(apps, preserve_sort=preserve_sort)
        self._adjust_name_column_width()
        self.table.setUpdatesEnabled(True)
        if not skip_width_hint:
            self._emit_table_width_hint()

    def _set_data(self, apps: List[AppInfo], preserve_sort: bool = False):
        self._last_apps = list(apps)
        self._group_names = {gid: name for gid, name, _c in AppRepository.get_all_groups()}
        self.table.setUpdatesEnabled(False)
        self._sort.begin_refresh()
        captured = self._sort.capture_order() if preserve_sort else None

        self._rows = {}
        for app in self._last_apps:
            st = RowState(
                app=app,
                base_focus=int(app.total_focus_seconds or 0),
                base_lifetime=int(app.total_lifetime_seconds or 0),
            )
            self._reset_row_status(st)
            self._rows[app.exe_path] = st
        self._render_rows()
        self._sort.apply_after_refresh(preserve_sort, captured)
        self.table.setUpdatesEnabled(True)

    # ---------- 行渲染（全部按稳定 ID） ----------

    def _render_rows(self):
        # 必须在关闭排序时逐行填充：排序开启且有指示器时，插入/写单元格会被
        # 立刻重排，导致行被移走、后续 setItem 落到错位行上（大量单元格丢失）。
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._row_paths = []
        for app in self._last_apps:
            st = self._rows.get(app.exe_path)
            if st is None:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._row_paths.append(app.exe_path)
            for col, cid in enumerate(self._visible_ids):
                item = self._render_cell(cid, st)
                item.setData(EXE_PATH_ROLE, app.exe_path)
                self.table.setItem(row, col, item)

    @staticmethod
    def _reset_row_status(st: RowState):
        """整表刷新时先按 is_watched / is_path_exist 给出初始状态。"""
        if not st.app.is_path_exist:
            st.status_value, st.status_text = -2, "路径不存在"
        elif not st.app.is_watched:
            st.status_value, st.status_text = -1, "未监视"
        else:
            st.status_value, st.status_text = 0, "未运行"
        st.running = False
        st.focused = False
        st.session_focus = _NOT_RUNNING
        st.session_lifetime = _NOT_RUNNING

    @staticmethod
    def _live_total(st: RowState, kind: str) -> int:
        if kind == "focus":
            return st.base_focus + (max(0, st.session_focus) if st.running else 0)
        return st.base_lifetime + (max(0, st.session_lifetime) if st.running else 0)

    def _render_cell(self, cid: str, st: RowState) -> QTableWidgetItem:
        app = st.app
        spec = tc.COLUMNS[cid]

        if cid == "status":
            key = _STATUS_VALUE_TO_KEY.get(st.status_value, "not_running")
            item = SortableTableWidgetItem("")
            item.setData(Qt.UserRole, st.status_value)
            item.setIcon(self._create_status_icon(
                self._status_colors.get(key, self._status_colors["not_running"])))
            item.setToolTip(st.status_text)
            return item

        if cid == "icon":
            item = SortableTableWidgetItem("")
            item.setIcon(get_exe_icon(app.exe_path))
            return item

        if cid == "name":
            text = tc.display_name(app)
            if app.color_tags:
                dots = " ".join(f'<span style="color:{c};">●</span>' for c in app.color_tags)
                text = f"{text}  {dots}"
            item = SortableTableWidgetItem(text)
            item.setData(Qt.UserRole, app.exe_path)
            return item

        if cid == "exe_name":
            item = SortableTableWidgetItem(app.exe_name or "")
            item.setData(Qt.UserRole, (app.exe_name or "").lower())
            return item

        if cid == "exe_path":
            item = SortableTableWidgetItem(app.exe_path or "")
            item.setToolTip(app.exe_path or "")
            return item

        if cid == "launch_path":
            item = SortableTableWidgetItem(app.launch_path or "—")
            item.setToolTip(app.launch_path or "")
            return item

        if cid == "launch_with_le":
            item = SortableTableWidgetItem("是" if app.launch_with_le else "否")
            item.setData(Qt.UserRole, int(bool(app.launch_with_le)))
            return item

        if cid == "is_watched":
            item = SortableTableWidgetItem("是" if app.is_watched else "否")
            item.setData(Qt.UserRole, int(bool(app.is_watched)))
            return item

        if cid == "groups":
            names = "、".join(self._group_names.get(gid, "") for gid in (app.group_ids or []))
            names = names.strip("、")
            item = SortableTableWidgetItem(names or "—")
            item.setData(Qt.UserRole, names)
            return item

        if cid == "focus_ratio":
            life = self._live_total(st, "lifetime")
            ratio = (self._live_total(st, "focus") / life) if life else 0
            item = SortableTableWidgetItem(f"{ratio * 100:.0f}%")
            item.setData(Qt.UserRole, round(ratio, 4))
            return item

        if cid == "session_focus":
            na = st.session_focus == _NOT_RUNNING
            item = SortableTableWidgetItem("" if na else format_seconds_to_text(st.session_focus))
            item.setData(Qt.UserRole, _NOT_RUNNING if na else st.session_focus)
            return item

        if cid == "session_lifetime":
            na = st.session_lifetime == _NOT_RUNNING
            item = SortableTableWidgetItem("" if na else format_seconds_to_text(st.session_lifetime))
            item.setData(Qt.UserRole, _NOT_RUNNING if na else st.session_lifetime)
            return item

        if cid == "last_started_at":
            item = SortableTableWidgetItem(app.last_start_at)
            item.setData(Qt.UserRole, app.last_start_at_ts or 0)
            return item

        if cid == "first_seen_at":
            item = SortableTableWidgetItem(app.first_seen_at)
            item.setData(Qt.UserRole, app.first_seen_at_ts or 0)
            return item

        if cid == "last_ended_at":
            item = SortableTableWidgetItem(app.last_ended_at or "—")
            item.setData(Qt.UserRole, app.last_ended_at_ts or 0)
            return item

        if cid == "total_focus":
            value = self._live_total(st, "focus")
            item = SortableTableWidgetItem(format_seconds_to_text(value))
            item.setData(Qt.UserRole, value)
            return item

        if cid == "total_lifetime":
            value = self._live_total(st, "lifetime")
            item = SortableTableWidgetItem(format_seconds_to_text(value))
            item.setData(Qt.UserRole, value)
            return item

        if spec.kind == "placeholder":
            return SortableTableWidgetItem("—")
        return SortableTableWidgetItem("")

    def exe_path_at_row(self, row: int) -> str:
        """当前视觉行的 exe_path（排序/拖拽换序后依旧准确）。"""
        if row < 0 or row >= self.table.rowCount():
            return ""
        item = self.table.item(row, 0)
        if item is not None:
            path = item.data(EXE_PATH_ROLE)
            if path:
                return path
        for col in range(1, self.table.columnCount()):
            other = self.table.item(row, col)
            if other is not None:
                path = other.data(EXE_PATH_ROLE)
                if path:
                    return path
        return ""

    def _row_index(self, exe_path: str) -> int:
        """exe_path → 当前视觉行号（找不到返回 -1）。"""
        if not exe_path:
            return -1
        for row in range(self.table.rowCount()):
            if self.exe_path_at_row(row) == exe_path:
                return row
        return -1

    def _write_row(self, st: RowState, row: Optional[int] = None):
        """把某行“会随运行变化”的列按 ID 写回；row 缺省时按行身份解析。"""
        if row is None:
            row = self._row_index(st.app.exe_path)
        if row < 0:
            return
        for cid in ("status", "session_focus", "session_lifetime",
                    "total_focus", "total_lifetime", "focus_ratio"):
            col = self.col_index(cid)
            if col < 0:
                continue
            item = self._render_cell(cid, st)
            item.setData(EXE_PATH_ROLE, st.app.exe_path)
            self.table.setItem(row, col, item)

    def update_status(self, status_data: dict):
        self.table.setUpdatesEnabled(False)
        for row in range(self.table.rowCount()):
            exe_path = self.exe_path_at_row(row)
            st = self._rows.get(exe_path)
            if st is None:
                continue
            app = st.app
            if not app.is_path_exist:
                st.status_value, st.status_text = -2, "路径不存在"
                st.running = False
                st.focused = False
                st.session_focus = _NOT_RUNNING
                st.session_lifetime = _NOT_RUNNING
                self._write_row(st, row)
                continue
            if not app.is_watched:
                st.status_value, st.status_text = -1, "未监视"
                st.running = False
                st.focused = False
                st.session_focus = _NOT_RUNNING
                st.session_lifetime = _NOT_RUNNING
                self._write_row(st, row)
                continue

            data = status_data.get(app.exe_path)
            if data:
                st.running = True
                st.focused = bool(data.get("is_focused"))
                st.session_focus = int(data.get("focus", 0))
                st.session_lifetime = int(data.get("runtime_seconds", 0))
                st.status_value = 2 if st.focused else 1
                st.status_text = "已聚焦" if st.focused else "运行中"
            elif st.running:
                # 刚结束：把本次并入基准（下一次整表刷新会用库里的权威值覆盖）
                st.base_focus += max(0, st.session_focus)
                st.base_lifetime += max(0, st.session_lifetime)
                st.running = False
                st.focused = False
                st.session_focus = _NOT_RUNNING
                st.session_lifetime = _NOT_RUNNING
                st.status_value, st.status_text = 0, "未运行"
            else:
                continue
            self._write_row(st, row)
        self._sort.apply_after_status_update()
        self.table.setUpdatesEnabled(True)

    def set_row_watched_state(self, exe_path: str, watched: bool):
        """只更新指定行的监视状态，不重建整张表。"""
        st = self._rows.get(exe_path)
        if st is None:
            return
        st.app.is_watched = watched
        if not watched:
            st.status_value, st.status_text = -1, "未监视"
            st.running = False
            st.focused = False
            st.session_focus = _NOT_RUNNING
            st.session_lifetime = _NOT_RUNNING
        else:
            st.status_value, st.status_text = 0, "未运行"
        self._write_row(st)

    def _on_double_clicked(self, index):
        if self._editing_rename:
            return
        row = index.row()
        exe_path = self._get_exe_path_by_row(row)
        if not exe_path:
            return
        action = "launch"
        if self._settings is not None:
            action = str(self._settings.get("tableDoubleClickAction", "launch")).lower()
        if action == "detail":
            self.detail_requested.emit(exe_path)
        else:
            self.launch_requested.emit(exe_path, False)

    def _on_context_menu(self, pos):
        row = self.table.currentRow()
        if row < 0:
            return

        exe_path = self._get_exe_path_by_row(row)
        if not exe_path:
            return
        app_info = self._app_for_path(exe_path)
        if app_info is None:
            return

        exe_name = app_info.exe_name
        is_watched = bool(app_info.is_watched)

        menu = QMenu()
        detail_action = menu.addAction("查看详细信息")
        rename_action = menu.addAction("重命名...")
        launch_action = menu.addAction("启动此应用")
        le_launch_action = None
        app_info = self._app_for_path(exe_path)
        if should_offer_le_launch(getattr(app_info, "launch_with_le", False)):
            le_launch_action = menu.addAction("本次用 Locale Emulator 启动")
        menu.addSeparator()
        toggle_watch_action = menu.addAction("停止监视" if is_watched else "恢复监视")

        # 分组子菜单
        group_menu = menu.addMenu("分组")
        manage_groups_action = group_menu.addAction("管理分组...")
        group_menu.addSeparator()
        all_groups = AppRepository.get_all_groups()
        current_groups = [gid for gid, _ in AppRepository.get_app_groups(exe_path)]

        def _dot_icon(color):
            if not color:
                return
            pix = QPixmap(12, 12)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(1, 1, 10, 10)
            painter.end()
            return QIcon(pix)

        group_actions = {}
        for gid, gname, color in all_groups:
            act = group_menu.addAction(gname)
            act.setCheckable(True)
            act.setChecked(gid in current_groups)
            if color:
                act.setIcon(_dot_icon(color))
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
        elif action == rename_action:
            self._start_inline_rename(row, exe_path, self._display_name_of(exe_path))
        elif action == launch_action:
            self.launch_requested.emit(exe_path, False)
        elif le_launch_action is not None and action == le_launch_action:
            self.launch_requested.emit(exe_path, True)
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

    # --- 内联重命名（基于 QTableWidget.editItem 原生机制）---

    def _on_f2_press(self):
        """F2 快捷键：对当前选中行触发内联重命名。"""
        row = self.table.currentRow()
        if row < 0:
            return
        name_col = self.col_index("name")
        if name_col < 0:
            return
        exe_path = self._get_exe_path_by_row(row)
        if not exe_path:
            return
        self._start_inline_rename(row, exe_path, self._display_name_of(exe_path))

    def _display_name_of(self, exe_path: str) -> str:
        """当前显示名（自定义名 ▸ 回退 EXE 名），用于重命名预填。"""
        st = self._rows.get(exe_path)
        if st is not None:
            return tc.display_name(st.app)
        app = self._app_for_path(exe_path)
        return tc.display_name(app) if app is not None else ""

    def _start_inline_rename(self, row: int, exe_path: str, original_name: str):
        """临时切换 editTriggers 为 DoubleClicked，调用 editItem 弹出 Qt 原生编辑器。
        通过委托的 createEditor 创建无边框编辑器，通过 editingFinished 信号触发保存。"""
        name_col = self.col_index("name")
        if name_col < 0:
            return
        self._editing_rename = True
        self._rename_row = row
        self._rename_exe_path = exe_path
        self._rename_original = original_name
        self._rename_editor_widget = None
        self._restore_edit_triggers = self.table.editTriggers()
        self.table.setSortingEnabled(False)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked)
        self.table.setCurrentCell(row, name_col)
        self.table.editItem(self.table.item(row, name_col))
        self.table.setEditTriggers(self._restore_edit_triggers)
        app = QApplication.instance()
        if app:
            editor = app.focusWidget()
            if editor:
                self._rename_editor_widget = editor
                self._rename_original = editor.text()
                if "\u2003" in self._rename_original:
                    self._rename_original = self._rename_original.split("\u2003")[0].strip()
                editor.editingFinished.connect(self._commit_rename)
                editor._orig_keypress = editor.keyPressEvent
                def kp_override(evt):
                    if evt.key() == Qt.Key_Escape:
                        self._cancel_rename()
                        return
                    editor._orig_keypress(evt)
                editor.keyPressEvent = kp_override

    def _commit_rename(self):
        """编辑器提交（Enter / 焦点离开），从编辑器读取新名字写入 DB。"""
        if not self._editing_rename:
            return
        self._editing_rename = False
        self._restore_editor_keypress()
        editor = self._rename_editor_widget
        if not editor:
            self.table.setSortingEnabled(True)
            return
        new_name = editor.text().strip()
        if "\u2003" in new_name:
            new_name = new_name.split("\u2003")[0].strip()
        if new_name == self._rename_original:
            self.table.setSortingEnabled(True)
            return
        ok = AppRepository.rename_app(self._rename_exe_path, new_name)
        if not ok:
            QMessageBox.warning(self.table, "提示", "名称保存失败，请重试。")
        else:
            st = self._rows.get(self._rename_exe_path)
            if st is not None:
                st.app.custom_name = new_name
        self._refresh_color_dots(self._rename_row, self._rename_exe_path)
        self.table.setSortingEnabled(True)
        self._rename_row = -1
        self._rename_exe_path = ""
        self._rename_original = ""
        self._rename_editor_widget = None

    def _cancel_rename(self):
        """Esc 取消：恢复原名字。"""
        if not self._editing_rename:
            return
        self._editing_rename = False
        self._restore_editor_keypress()
        name_col = self.col_index("name")
        name_item = self.table.item(self._rename_row, name_col) if name_col >= 0 else None
        if name_item:
            name_item.setText(self._rename_original)
            self._refresh_color_dots(self._rename_row, self._rename_exe_path)
        self.table.setSortingEnabled(True)
        self._rename_row = -1
        self._rename_exe_path = ""
        self._rename_original = ""
        self._rename_editor_widget = None

    def _restore_editor_keypress(self):
        """恢复编辑器原始 keyPressEvent。"""
        editor = self._rename_editor_widget
        if editor and hasattr(editor, '_orig_keypress'):
            editor.keyPressEvent = editor._orig_keypress

    def _refresh_color_dots(self, row: int, exe_path: str):
        """更新名称列的颜色圆点（名称本身按“自定义名 ▸ EXE 名”口径重算）。"""
        col = self.col_index("name")
        if col < 0:
            return
        name_item = self.table.item(row, col)
        if not name_item:
            return
        st = self._rows.get(exe_path)
        base_name = tc.display_name(st.app) if st is not None else name_item.text()
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
        return self.exe_path_at_row(row)

    def _app_for_path(self, exe_path: str):
        st = self._rows.get(exe_path)
        if st is not None:
            return st.app
        for app in self._last_apps:
            if app.exe_path == exe_path:
                return app
        return None

    def cancel_sort_preserve(self):
        self._sort.unfreeze()

    def _adjust_name_column_width(self):
        name_col = self.col_index("name")
        if name_col < 0:
            return

        cell_fm = QFontMetrics(self.table.font())
        header_fm = QFontMetrics(self.table.horizontalHeader().font())

        header_item = self.table.horizontalHeaderItem(name_col)
        header_text = header_item.text() if header_item else "名称"

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


class _NameEditorDelegate(QStyledItemDelegate):
    """名称列内联编辑器委托：无边框、透明背景、与表格行样式一致。"""

    def __init__(self, table):
        super().__init__(table)
        self._table = table

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        bg = option.palette.base().color().name()
        editor.setStyleSheet(f"""
            QLineEdit {{
                border: none;
                background: {bg};
                padding: 2px 6px;
            }}
            QLineEdit:focus {{
                border: none;
                outline: none;
                background: {bg};
            }}
        """)
        editor.setFont(option.font)
        editor.setFocusPolicy(Qt.StrongFocus)
        return editor

    def setEditorData(self, editor, index):
        item = self._table.item(index.row(), index.column())
        raw = item.text()
        raw = raw.split("  <span")[0]        # 去掉名称后的颜色圆点
        base = Path(raw).stem if Path(raw).suffix else raw
        editor.setText(base)

    def setModelData(self, editor, model, index):
        item = self._table.item(index.row(), index.column())
        new_text = editor.text()
        if new_text.strip():
            item.setText(new_text)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
