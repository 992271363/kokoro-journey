"""使用行为分析对话框：时段分布 / 7×24 热力图 / 画像 / 应用与对比。"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPolygonF, QColor, QPen, QBrush, QFont,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QButtonGroup,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialogButtonBox,
)

from PySide6.QtCharts import (
    QChartView, QChart, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
)

from core import analysis as an
from util.config import Settings
from util.format import format_seconds_to_text
from ui.theme import get_system_theme

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
RADAR_ORDER = ["专注度", "规律性", "时长", "集中度", "活跃度"]

# 热力图：每 3 小时一个刻度（格子过窄时自动退化为每 6 小时）
HOUR_TICKS = [0, 3, 6, 9, 12, 15, 18, 21]
_HEAT_GAP = 3.0
_HEAT_TIERS = 5  # 5 档离散色阶

# 5 档色板（不使用 alpha 表达强度；0 值不填充，仅极淡描边）
# 统一逻辑：越少越浅黄绿、越多越深绿（禁止按主题反转方向）。
# 两个色板都必须满足 L* 递减（越浓越深）；深色只是在同方向上整体浅一档，
# 避免深绿末档压在深色底上显得发闷。
#   浅色（白底）：YlGn5
#   深色（#1e293b 底）：同方向浅一档
_HEAT_TIER_COLORS = {
    False: ("#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"),
    True: ("#ffffcc", "#d9f0a3", "#a1d99b", "#74c476", "#31a354"),
}
# 空槽：极淡细描边（接近背景，只提示 7×24 槽位结构，不产生“数据”感）
_HEAT_EMPTY_OUTLINE = {False: "#eceef1", True: "#2a3546"}
# 文案与主题无关：两个主题的色阶方向一致
_HEAT_DESC = "颜色越深表示专注越多"


def _is_dark_theme() -> bool:
    """与 window.py:_is_dark_theme 同逻辑：显式模式优先，否则跟随系统。"""
    mode = Settings().get("themeMode", "system")
    if mode == "dark":
        return True
    if mode == "light":
        return False
    return get_system_theme() == "dark"


def heat_cap(matrix) -> int:
    """稳健上限：非零值的 p95，且不低于峰值的 35%（避免单个尖峰压平全图）。"""
    values = [int(v) for row in matrix for v in row if v > 0]
    if not values:
        return 0
    values.sort()
    p95 = values[int(round(0.95 * (len(values) - 1)))]
    peak = values[-1]
    return max(1, int(max(p95, peak * 0.35)))


def heat_level(value: int, cap: int) -> int:
    """强度 → 档位：p95+sqrt 压缩后 5 等分（绝对强度语义，不用 quantile）。

    返回 0（空）/ 1..5。
    """
    if value <= 0 or cap <= 0:
        return 0
    t = min(1.0, math.sqrt(value / cap))
    return min(_HEAT_TIERS, max(1, int(math.ceil(t * _HEAT_TIERS))))


def heat_color(value: int, cap: int, dark: bool) -> QColor:
    """档位对应颜色；0 值返回透明（绘制时空槽只描边、不填充）。"""
    level = heat_level(value, cap)
    if level == 0:
        return QColor(0, 0, 0, 0)
    return QColor(_HEAT_TIER_COLORS[bool(dark)][level - 1])


class HeatmapWidget(QWidget):
    """7×24 专注热力图（行=星期，列=小时）。

    自绘圆角小方块：不受全局 QTableWidget QSS（hover/边框）影响，任意尺寸
    都保持等比小方块；颜色按强度取色，支持浅/深色主题与悬停提示。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._matrix = [[0] * 24 for _ in range(7)]
        self._cap = 0
        self._dark = _is_dark_theme()
        self._hover = None
        self.setMouseTracking(True)
        self.setMinimumHeight(200)

    # ---------- 数据 / 主题 ----------

    def set_matrix(self, matrix, dark=None):
        self._matrix = [list(row) for row in matrix]
        self._cap = heat_cap(self._matrix)
        if dark is not None:
            self._dark = bool(dark)
        self.update()

    def set_dark(self, dark: bool):
        if bool(dark) != self._dark:
            self._dark = bool(dark)
            self.update()

    def showEvent(self, event):  # noqa: N802
        self._dark = _is_dark_theme()
        super().showEvent(event)

    # ---------- 布局 ----------

    def _metrics(self, w, h):
        """返回 (x0, y0, cell, gap, grid_w, grid_h)；空间不足时 cell 有下限。"""
        pad_left, pad_right = 42.0, 10.0
        pad_top, pad_bottom = 26.0, 22.0
        gw = max(1.0, w - pad_left - pad_right)
        gh = max(1.0, h - pad_top - pad_bottom)
        gap = _HEAT_GAP
        cell = min((gw - gap * 23) / 24.0, (gh - gap * 6) / 7.0)
        cell = max(3.0, cell)
        grid_w = cell * 24 + gap * 23
        grid_h = cell * 7 + gap * 6
        x0 = pad_left + max(0.0, (gw - grid_w) / 2.0)
        y0 = pad_top + max(0.0, (gh - grid_h) / 2.0)
        return x0, y0, cell, gap, grid_w, grid_h

    def _cell_at(self, pos):
        x0, y0, cell, gap, grid_w, grid_h = self._metrics(self.width(), self.height())
        if cell <= 0:
            return None
        col = int((pos.x() - x0) // (cell + gap))
        row = int((pos.y() - y0) // (cell + gap))
        if 0 <= row < 7 and 0 <= col < 24:
            # 落在间隙里不算命中
            cx = x0 + col * (cell + gap)
            cy = y0 + row * (cell + gap)
            if cx <= pos.x() <= cx + cell and cy <= pos.y() <= cy + cell:
                return row, col
        return None

    # ---------- 绘制 ----------

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        x0, y0, cell, gap, grid_w, grid_h = self._metrics(w, h)
        label_color = QColor("#e2e8f0") if self._dark else QColor("#52525b")
        radius = min(4.0, max(1.5, cell * 0.18))
        outline = QColor(_HEAT_EMPTY_OUTLINE[self._dark])

        def cell_rect(r, c):
            return QRectF(x0 + c * (cell + gap), y0 + r * (cell + gap), cell, cell)

        # 星期标签（左）
        painter.setPen(label_color)
        for r, name in enumerate(WEEKDAY_NAMES):
            cy = y0 + r * (cell + gap)
            painter.drawText(QRectF(0, cy, x0 - 6, cell), Qt.AlignRight | Qt.AlignVCenter, name)

        # 小时刻度（下），格子窄时退化为每 6 小时
        ticks = HOUR_TICKS if cell >= 14 else HOUR_TICKS[::2]
        for hh in ticks:
            cx = x0 + hh * (cell + gap)
            painter.drawText(QRectF(cx - 12, y0 + grid_h + 4, cell + 24, 14),
                             Qt.AlignHCenter | Qt.AlignTop, str(hh))

        # 方块：空槽只描极淡边（提示槽位结构），有数据按档位填充
        for r in range(7):
            for c in range(24):
                value = self._matrix[r][c]
                rect = cell_rect(r, c)
                color = heat_color(value, self._cap, self._dark)
                if color.alpha() == 0:
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(QPen(outline, 1))
                else:
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(rect, radius, radius)

        # 悬停高亮
        if self._hover is not None:
            r, c = self._hover
            accent = QColor("#93c5fd") if self._dark else QColor(29, 78, 216)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(accent, 1.5))
            painter.drawRoundedRect(cell_rect(r, c).adjusted(-1, -1, 1, 1),
                                    radius + 1, radius + 1)

        # 无数据：保留空网格，仅叠加提示，不画色例
        if self._cap <= 0:
            painter.setPen(label_color)
            painter.drawText(self.rect(), Qt.AlignCenter, "该范围暂无数据")
            painter.end()
            return

        # 色例（右上）：5 个离散档位方块 + 少 / 多
        sw, sh, sgap = 16.0, 12.0, 3.0
        total_w = sw * _HEAT_TIERS + sgap * (_HEAT_TIERS - 1)
        bx = w - 10 - total_w - 16
        by = 6.0
        for i in range(_HEAT_TIERS):
            rect = QRectF(bx + i * (sw + sgap), by, sw, sh)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(_HEAT_TIER_COLORS[self._dark][i])))
            painter.drawRoundedRect(rect, 2, 2)
        painter.setPen(label_color)
        painter.drawText(QRectF(bx - 20, by - 2, 18, 16), Qt.AlignRight | Qt.AlignVCenter, "少")
        painter.drawText(QRectF(bx + total_w + 4, by - 2, 18, 16),
                         Qt.AlignLeft | Qt.AlignVCenter, "多")

        painter.end()

    # ---------- 交互 ----------

    def mouseMoveEvent(self, event):  # noqa: N802
        loc = self._cell_at(event.position())
        if loc != self._hover:
            self._hover = loc
            if loc is None:
                self.setToolTip("")
            else:
                r, c = loc
                self.setToolTip(
                    f"{WEEKDAY_NAMES[r]} {c}:00 — {format_seconds_to_text(self._matrix[r][c])}"
                )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.setToolTip("")
            self.update()
        super().leaveEvent(event)



class RadarWidget(QWidget):
    """五维雷达图（自绘，避免 Qt 极坐标轴的不确定性）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dims = {k: 0.0 for k in RADAR_ORDER}
        self.setMinimumSize(260, 260)

    def set_data(self, dims: dict):
        self._dims = {k: float(dims.get(k, 0.0)) for k in RADAR_ORDER}
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 + 8
        radius = min(w, h) / 2 - 44
        n = len(RADAR_ORDER)

        # 网格环
        painter.setPen(QPen(QColor(200, 205, 215), 1))
        for ring in (0.25, 0.5, 0.75, 1.0):
            poly = QPolygonF()
            for i in range(n):
                ang = -math.pi / 2 + i * 2 * math.pi / n
                poly.append(QPointF(cx + radius * ring * math.cos(ang),
                                    cy + radius * ring * math.sin(ang)))
            painter.drawPolygon(poly)

        # 轴线 + 标签
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        for i in range(n):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            ex = cx + radius * math.cos(ang)
            ey = cy + radius * math.sin(ang)
            painter.setPen(QPen(QColor(180, 185, 195), 1))
            painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))
            lx = cx + (radius + 20) * math.cos(ang)
            ly = cy + (radius + 20) * math.sin(ang)
            painter.setPen(QColor(70, 80, 95))
            painter.drawText(QRectF(lx - 34, ly - 10, 68, 20),
                             Qt.AlignCenter, f"{RADAR_ORDER[i]} {self._dims[RADAR_ORDER[i]]:.0f}")

        # 数值多边形
        poly = QPolygonF()
        for i in range(n):
            ang = -math.pi / 2 + i * 2 * math.pi / n
            v = max(0.0, min(100.0, self._dims[RADAR_ORDER[i]])) / 100.0
            poly.append(QPointF(cx + radius * v * math.cos(ang),
                                cy + radius * v * math.sin(ang)))
        painter.setPen(QPen(QColor(56, 132, 255), 2))
        painter.setBrush(QBrush(QColor(56, 132, 255, 70)))
        painter.drawPolygon(poly)
        painter.end()


class AnalysisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("分析")
        self.resize(920, 660)
        self._scope = an.SCOPE_TODAY
        self._metric = 0  # 0 专注 / 1 打开 / 2 关闭

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 顶部：时间范围
        bar = QHBoxLayout()
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        self._scope_btns = {}
        for scope in (an.SCOPE_TODAY, an.SCOPE_WEEK, an.SCOPE_30D, an.SCOPE_ALL):
            b = QPushButton(an.SCOPE_LABELS[scope])
            b.setCheckable(True)
            b.setProperty("stat_mode", True)
            b.setFixedHeight(32)
            b.setFixedWidth(84)
            b.clicked.connect(lambda _c=False, s=scope: self._set_scope(s))
            bar.addWidget(b)
            self.scope_group.addButton(b)
            self._scope_btns[scope] = b
        self._scope_btns[an.SCOPE_TODAY].setChecked(True)
        bar.addStretch()
        root.addLayout(bar)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self._build_tab_hours()
        self._build_tab_heatmap()
        self._build_tab_persona()
        self._build_tab_apps()

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._reload()

    # ---------------- 构建各页 ----------------

    def _build_tab_hours(self):
        page = QWidget()
        lay = QVBoxLayout(page)

        top = QHBoxLayout()
        top.addWidget(QLabel("指标:"))
        self.metric_group = QButtonGroup(self)
        for idx, name in enumerate(("专注", "打开", "关闭")):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setFixedWidth(72)
            b.setChecked(idx == 0)
            b.clicked.connect(lambda _c=False, i=idx: self._set_metric(i))
            top.addWidget(b)
            self.metric_group.addButton(b)
        top.addStretch()
        lay.addLayout(top)

        self.hour_chart_view = QChartView()
        self.hour_chart_view.setRenderHint(QPainter.Antialiasing)
        lay.addWidget(self.hour_chart_view, stretch=1)
        self.tabs.addTab(page, "时段分布")

    def _build_tab_heatmap(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.heat_desc = QLabel("专注热力图（行=星期，列=小时）")
        lay.addWidget(self.heat_desc)
        self.heat_hint = QLabel("当前范围数据较少，建议切换更大范围查看")
        self.heat_hint.setProperty("role", "muted")
        self.heat_hint.setVisible(False)
        lay.addWidget(self.heat_hint)
        self.heat = HeatmapWidget()
        lay.addWidget(self.heat, stretch=1)
        self.tabs.addTab(page, "热力图")

    def _build_tab_persona(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.persona_labels = QLabel("")
        self.persona_labels.setWordWrap(True)
        self.persona_labels.setObjectName("summary_label")
        lay.addWidget(self.persona_labels)
        self.persona_summary = QLabel("")
        self.persona_summary.setWordWrap(True)
        lay.addWidget(self.persona_summary)

        self.radar = RadarWidget()
        lay.addWidget(self.radar, stretch=1, alignment=Qt.AlignCenter)
        self.tabs.addTab(page, "画像")

    def _build_tab_apps(self):
        page = QWidget()
        lay = QVBoxLayout(page)

        self.cmp_label = QLabel("")
        self.cmp_label.setWordWrap(True)
        self.cmp_label.setObjectName("summary_label")
        lay.addWidget(self.cmp_label)

        self.app_table = QTableWidget(0, 6)
        self.app_table.setHorizontalHeaderLabels(
            ["应用", "高峰时段", "专注时长", "活跃天数", "平均单次", "专注占比"])
        self.app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            self.app_table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.app_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.app_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.app_table.setAlternatingRowColors(True)
        lay.addWidget(self.app_table, stretch=1)
        self.tabs.addTab(page, "应用与对比")

    # ---------------- 交互 ----------------

    def _set_scope(self, scope: str):
        if scope == self._scope:
            return
        self._scope = scope
        self._reload()

    def _set_metric(self, idx: int):
        self._metric = idx
        self._refresh_hours()

    # ---------------- 刷新 ----------------

    def _reload(self):
        an.clear_analysis_cache()
        self._refresh_hours()
        self._refresh_heatmap()
        self._refresh_persona()
        self._refresh_apps()

    def _refresh_hours(self):
        if self._metric == 0:
            values = an.get_hourly_focus(self._scope)
            title, unit, div = "专注时长（小时）", "小时", 3600.0
        elif self._metric == 1:
            values = an.get_hourly_opens(self._scope)
            title, unit, div = "打开次数", "次", 1.0
        else:
            values = an.get_hourly_closes(self._scope)
            title, unit, div = "关闭次数", "次", 1.0

        chart = QChart()
        chart.setTitle(title)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        series = QBarSeries()
        bar = QBarSet(unit)
        for v in values:
            bar.append(v / div)
        series.append(bar)
        chart.addSeries(series)

        ax = QBarCategoryAxis()
        ax.append([str(h) for h in range(24)])
        chart.addAxis(ax, Qt.AlignBottom)
        series.attachAxis(ax)
        ay = QValueAxis()
        ay.setTitleText(unit)
        chart.addAxis(ay, Qt.AlignLeft)
        series.attachAxis(ay)
        chart.legend().setVisible(False)
        self.hour_chart_view.setChart(chart)

    def _refresh_heatmap(self):
        matrix = an.get_weekday_hour_matrix(self._scope)
        dark = _is_dark_theme()
        self.heat.set_matrix(matrix, dark)
        self.heat_desc.setText(f"专注热力图（行=星期，列=小时；{_HEAT_DESC}）")
        # 稀疏提示：只有 1 天（或 0 天）有数据时，7×24 热力图没有意义
        active_weekdays = sum(1 for row in matrix if any(row))
        self.heat_hint.setVisible(active_weekdays <= 1)

    def _refresh_persona(self):
        p = an.get_persona(self._scope)
        self.persona_labels.setText("标签：" + "、".join(p.labels) if p.labels else "标签：—")
        self.persona_summary.setText(p.summary)
        self.radar.set_data(p.radar)

    def _refresh_apps(self):
        peaks = an.get_app_hour_peaks(self._scope)
        self.app_table.setRowCount(len(peaks))
        for row, s in enumerate(peaks):
            hour = f"{s.peak_hour:02d}:00" if s.peak_hour >= 0 else "—"
            cells = [
                s.app_name, hour, format_seconds_to_text(s.focus_seconds),
                str(s.active_days), format_seconds_to_text(s.avg_session_seconds),
                f"{s.focus_ratio * 100:.0f}%",
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c > 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.app_table.setItem(row, c, item)

        cmp = an.get_comparison(self._scope)
        self.cmp_label.setText(self._format_comparison(cmp))

    @staticmethod
    def _fmt_range(start, end) -> str:
        return f"{start:%m-%d %H:%M} ~ {end:%m-%d %H:%M}"

    def _format_comparison(self, cmp) -> str:
        if cmp is None:
            return "全部范围不做对比。"
        cur, prev, d = cmp["current"], cmp["previous"], cmp["delta"]
        align = "（对齐已过时长）" if cmp["aligned"] else "（同长度窗口）"
        pct = "" if d["focus_pct"] is None else f"（{d['focus_pct']:+.1f}%）"
        return (
            f"<b>对比</b>{align}<br>"
            f"本期 {self._fmt_range(cur['start'], cur['end'])}："
            f"专注 {format_seconds_to_text(cur['focus'])}、运行 {format_seconds_to_text(cur['lifetime'])}"
            f"、打开 {cur['opens']} / 关闭 {cur['closes']}<br>"
            f"上期 {self._fmt_range(prev['start'], prev['end'])}："
            f"专注 {format_seconds_to_text(prev['focus'])}、运行 {format_seconds_to_text(prev['lifetime'])}"
            f"、打开 {prev['opens']} / 关闭 {prev['closes']}<br>"
            f"专注增减 {format_seconds_to_text(d['focus'])}{pct}，运行增减 {format_seconds_to_text(d['lifetime'])}"
        )
