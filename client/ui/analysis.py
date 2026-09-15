"""使用行为分析对话框：时段分布 / 7×24 热力图 / 画像 / 应用与对比。"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPolygonF, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QButtonGroup,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialogButtonBox,
)

from PySide6.QtCharts import (
    QChartView, QChart, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
)

from core import analysis as an
from util.format import format_seconds_to_text

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
RADAR_ORDER = ["专注度", "规律性", "时长", "集中度", "活跃度"]


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
        lay.addWidget(QLabel("专注热力图（行=星期，列=小时；颜色越深专注越多）"))
        self.heat_table = QTableWidget(7, 24)
        self.heat_table.setVerticalHeaderLabels(WEEKDAY_NAMES)
        self.heat_table.setHorizontalHeaderLabels([str(h) for h in range(24)])
        self.heat_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.heat_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.heat_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.heat_table.setSelectionMode(QAbstractItemView.NoSelection)
        lay.addWidget(self.heat_table, stretch=1)
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
        peak = max((max(row) for row in matrix), default=0)
        for r in range(7):
            for c in range(24):
                v = matrix[r][c]
                item = QTableWidgetItem("" if v == 0 else str(v // 60))
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(f"{WEEKDAY_NAMES[r]} {c}:00 — {format_seconds_to_text(v)}")
                item.setBackground(self._heat_color(v, peak))
                self.heat_table.setItem(r, c, item)

    @staticmethod
    def _heat_color(value: int, peak: int) -> QColor:
        if peak <= 0 or value <= 0:
            return QColor(245, 247, 250)
        ratio = value / peak
        r = int(220 - 185 * ratio)
        g = int(232 - 130 * ratio)
        b = int(248 - 40 * ratio)
        return QColor(r, g, b)

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
