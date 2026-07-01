from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QStackedWidget,
    QHeaderView, QDialogButtonBox, QAbstractItemView, QSizePolicy,
    QButtonGroup, QWidget
)

from ui.widgets import AlwaysDownComboBox
from PySide6.QtCharts import (
    QChartView, QChart, QBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis, QPieSeries, QPieSlice
)

from core.stats import (
    get_weekly_stats, get_monthly_stats,
    get_recent_daily_stats, get_all_daily_stats,
    get_weekly_detail, get_monthly_detail, get_daily_detail,
    AppPeriodStat, PeriodStat,
)
from util.format import format_seconds_to_text


class StatsDialog(QDialog):
    """统计对话框，支持 最近/每月/每周/全部 四种模式切换。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_key: str = ""
        self._current_detail: list[AppPeriodStat] = []
        self._sort_by_focus = True
        self._period_sort_mode = 0
        self._period_stats: list[PeriodStat] = []
        self._current_mode = "recent"  # recent / monthly / weekly / all

        self.setWindowTitle("统计")
        self.resize(900, 600)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ---- 顶部模式切换栏 ----
        mode_bar = QHBoxLayout()
        mode_bar.setSpacing(6)
        mode_bar.setAlignment(Qt.AlignLeft)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.btn_mode_recent = QPushButton("最近")
        self.btn_mode_monthly = QPushButton("每月")
        self.btn_mode_weekly = QPushButton("每周")
        self.btn_mode_all = QPushButton("全部")

        for btn in (self.btn_mode_recent, self.btn_mode_monthly, self.btn_mode_weekly, self.btn_mode_all):
            btn.setCheckable(True)
            btn.setProperty("stat_mode", True)
            btn.setFixedHeight(32)
            btn.setFixedWidth(80)
            mode_bar.addWidget(btn)
            self.mode_group.addButton(btn)

        self.btn_mode_recent.setChecked(True)
        mode_bar.addStretch()
        main_layout.addLayout(mode_bar)

        # 模式切换信号
        self.btn_mode_recent.clicked.connect(lambda: self._set_mode("recent"))
        self.btn_mode_monthly.clicked.connect(lambda: self._set_mode("monthly"))
        self.btn_mode_weekly.clicked.connect(lambda: self._set_mode("weekly"))
        self.btn_mode_all.clicked.connect(lambda: self._set_mode("all"))

        # ---- 主体：左侧列表 + 右侧详情 ----
        body = QHBoxLayout()
        body.setSpacing(12)

        # 左侧列表
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)
        left_label = QLabel("时间段列表")
        left_layout.addWidget(left_label)

        # 左侧排序下拉框
        left_sort_layout = QHBoxLayout()
        left_sort_layout.setSpacing(6)
        left_sort_layout.addWidget(QLabel("排序:"))
        self.period_sort_combo = AlwaysDownComboBox()
        self.period_sort_combo.addItems([
            "时间 (最新 → 最旧)",
            "时间 (最旧 → 最新)",
            "焦点时长 (高 → 低)",
            "焦点时长 (低 → 高)",
            "运行时长 (高 → 低)",
            "运行时长 (低 → 高)",
        ])
        self.period_sort_combo.setFixedWidth(180)
        self.period_sort_combo.currentIndexChanged.connect(self._on_period_sort_changed)
        left_sort_layout.addWidget(self.period_sort_combo)
        left_sort_layout.addStretch()
        left_layout.addLayout(left_sort_layout)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(380)
        self.list_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget)

        body.addLayout(left_layout, stretch=0)

        # 右侧详情
        right_layout = QVBoxLayout()
        right_layout.setSpacing(10)

        # 总览
        self.summary_label = QLabel("请选择一个时间段")
        self.summary_label.setStyleSheet("font-size: 13px; padding: 6px; background: #f1f5f9; border-radius: 6px;")
        right_layout.addWidget(self.summary_label)

        # 工具栏：排序 + 视图切换
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_sort_focus = QPushButton("按焦点时长")
        self.btn_sort_lifetime = QPushButton("按运行时长")
        self.btn_sort_focus.setCheckable(True)
        self.btn_sort_lifetime.setCheckable(True)
        self.btn_sort_focus.setChecked(True)
        self.btn_sort_focus.clicked.connect(lambda: self._set_sort(True))
        self.btn_sort_lifetime.clicked.connect(lambda: self._set_sort(False))

        toolbar.addWidget(QLabel("排序:"))
        toolbar.addWidget(self.btn_sort_focus)
        toolbar.addWidget(self.btn_sort_lifetime)
        toolbar.addStretch()

        self.btn_view_text = QPushButton("纯文字")
        self.btn_view_bar = QPushButton("柱形图")
        self.btn_view_pie = QPushButton("饼状图")
        for b in (self.btn_view_text, self.btn_view_bar, self.btn_view_pie):
            b.setCheckable(True)
            b.setFixedWidth(80)
        self.btn_view_text.setChecked(True)
        self.btn_view_text.clicked.connect(lambda: self._set_view(0))
        self.btn_view_bar.clicked.connect(lambda: self._set_view(1))
        self.btn_view_pie.clicked.connect(lambda: self._set_view(2))

        toolbar.addWidget(QLabel("视图:"))
        toolbar.addWidget(self.btn_view_text)
        toolbar.addWidget(self.btn_view_bar)
        toolbar.addWidget(self.btn_view_pie)

        right_layout.addLayout(toolbar)

        # 内容区域（三种视图）
        self.stack = QStackedWidget()

        # 1. 纯文字
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(["应用名称", "焦点时长", "运行时长", "焦点占比"])
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.stack.addWidget(self.table_widget)

        # 2. 柱形图
        self.bar_chart_view = QChartView()
        self.bar_chart_view.setRenderHint(QPainter.Antialiasing)
        self.stack.addWidget(self.bar_chart_view)

        # 3. 双饼图（焦点 + 运行）
        self._pie_container = QWidget()
        pie_layout = QVBoxLayout(self._pie_container)
        pie_layout.setContentsMargins(0, 0, 0, 0)
        self._pie_focus_view = QChartView()
        self._pie_focus_view.setRenderHint(QPainter.Antialiasing)
        self._pie_focus_view.setStyleSheet("border: none; background: transparent;")
        self._pie_lifetime_view = QChartView()
        self._pie_lifetime_view.setRenderHint(QPainter.Antialiasing)
        self._pie_lifetime_view.setStyleSheet("border: none; background: transparent;")
        pie_layout.addWidget(self._pie_focus_view, 1)
        pie_layout.addWidget(self._pie_lifetime_view, 1)
        self.stack.addWidget(self._pie_container)

        right_layout.addWidget(self.stack, stretch=1)
        body.addLayout(right_layout, stretch=1)

        main_layout.addLayout(body, stretch=1)

        # ---- 底部按钮 ----
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # ---- 加载数据 ----
        self._load_period_list()

    def _set_mode(self, mode: str):
        if self._current_mode == mode:
            return
        self._current_mode = mode
        self._current_key = ""
        self._current_detail = []
        self._period_sort_mode = 0
        self.period_sort_combo.blockSignals(True)
        self.period_sort_combo.setCurrentIndex(0)
        self.period_sort_combo.blockSignals(False)
        self._load_period_list()

    def _set_sort(self, by_focus: bool):
        self._sort_by_focus = by_focus
        self.btn_sort_focus.setChecked(by_focus)
        self.btn_sort_lifetime.setChecked(not by_focus)
        self._refresh_detail_views()

    def _set_view(self, index: int):
        for i, b in enumerate((self.btn_view_text, self.btn_view_bar, self.btn_view_pie)):
            b.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def _load_period_list(self):
        if self._current_mode == "recent":
            self._period_stats = get_recent_daily_stats()
        elif self._current_mode == "monthly":
            self._period_stats = get_monthly_stats()
        elif self._current_mode == "weekly":
            self._period_stats = get_weekly_stats()
        else:
            self._period_stats = get_all_daily_stats()
        self._apply_period_sort()

    def _on_period_sort_changed(self, index: int):
        self._period_sort_mode = index
        self._apply_period_sort()

    def _apply_period_sort(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        if not self._period_stats:
            item = QListWidgetItem("暂无数据")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.list_widget.addItem(item)
            self.list_widget.blockSignals(False)
            return

        stats = list(self._period_stats)
        mode = self._period_sort_mode
        if mode == 0:  # 时间降序
            stats.sort(key=lambda s: s.key, reverse=True)
        elif mode == 1:  # 时间升序
            stats.sort(key=lambda s: s.key)
        elif mode == 2:  # 焦点降序
            stats.sort(key=lambda s: s.total_focus_seconds, reverse=True)
        elif mode == 3:  # 焦点升序
            stats.sort(key=lambda s: s.total_focus_seconds)
        elif mode == 4:  # 运行降序
            stats.sort(key=lambda s: s.total_lifetime_seconds, reverse=True)
        elif mode == 5:  # 运行升序
            stats.sort(key=lambda s: s.total_lifetime_seconds)

        prev_key = self._current_key

        for stat in stats:
            text = (
                f"{stat.label}\n"
                f"  焦点: {format_seconds_to_text(stat.total_focus_seconds)}"
                f"  |  运行: {format_seconds_to_text(stat.total_lifetime_seconds)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, stat)
            item.setSizeHint(item.sizeHint() + QSize(0, 12))
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        # 恢复选中或默认第一项（此时 blockSignals 已解除，信号正常触发）
        if prev_key:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                stat: PeriodStat = item.data(Qt.UserRole)
                if stat and stat.key == prev_key:
                    self.list_widget.setCurrentRow(i)
                    return
        self.list_widget.setCurrentRow(0)

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        stat: PeriodStat = current.data(Qt.UserRole)
        if stat is None:
            return

        self._current_key = stat.key
        self.summary_label.setText(
            f"<b>{stat.label}</b> &nbsp;&nbsp;"
            f"总焦点: {format_seconds_to_text(stat.total_focus_seconds)} &nbsp;&nbsp;"
            f"总运行: {format_seconds_to_text(stat.total_lifetime_seconds)}"
        )

        try:
            if self._current_mode == "recent" or self._current_mode == "all":
                self._current_detail = get_daily_detail(stat.key)
            elif self._current_mode == "weekly":
                self._current_detail = get_weekly_detail(stat.key)
            else:
                self._current_detail = get_monthly_detail(stat.key)
        except (ValueError, Exception):
            self._current_detail = []

        self._refresh_detail_views()

    def _refresh_detail_views(self):
        detail = list(self._current_detail)
        detail.sort(
            key=lambda x: x.focus_seconds if self._sort_by_focus else x.lifetime_seconds,
            reverse=True,
        )

        total_focus = sum(d.focus_seconds for d in detail)
        total_lifetime = sum(d.lifetime_seconds for d in detail)

        self._refresh_text_view(detail, total_focus, total_lifetime)
        self._refresh_bar_chart(detail)
        self._refresh_pie_charts(detail, total_focus, total_lifetime)

    def _refresh_text_view(self, detail: list[AppPeriodStat], total_focus: int, total_lifetime: int):
        self.table_widget.setRowCount(len(detail))
        for row, app_stat in enumerate(detail):
            ratio = 0.0
            if total_focus > 0:
                ratio = (app_stat.focus_seconds / total_focus) * 100

            self.table_widget.setItem(row, 0, QTableWidgetItem(app_stat.app_name))
            self.table_widget.setItem(row, 1, QTableWidgetItem(format_seconds_to_text(app_stat.focus_seconds)))
            self.table_widget.setItem(row, 2, QTableWidgetItem(format_seconds_to_text(app_stat.lifetime_seconds)))
            self.table_widget.setItem(row, 3, QTableWidgetItem(f"{ratio:.1f}%"))

            for col in (1, 2, 3):
                self.table_widget.item(row, col).setTextAlignment(Qt.AlignCenter)

    def _refresh_bar_chart(self, detail: list[AppPeriodStat]):
        chart = QChart()
        chart.setTitle("软件使用分布")
        chart.setAnimationOptions(QChart.SeriesAnimations)

        if not detail:
            chart.setTitle("暂无数据")
            self.bar_chart_view.setChart(chart)
            return

        series = QBarSeries()
        set_focus = QBarSet("焦点时长")
        set_lifetime = QBarSet("运行时长")
        categories = []

        for i, app_stat in enumerate(detail):
            categories.append(f"{i+1}. {app_stat.app_name}")
            set_focus.append(app_stat.focus_seconds / 3600.0)
            set_lifetime.append(app_stat.lifetime_seconds / 3600.0)

        series.append(set_focus)
        series.append(set_lifetime)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setTitleText("小时")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)

        self.bar_chart_view.setChart(chart)

    def _refresh_pie_charts(self, detail: list[AppPeriodStat],
                             total_focus: int, total_lifetime: int):
        self._build_pie(self._pie_focus_view, detail, total_focus, "focus")
        self._build_pie(self._pie_lifetime_view, detail, total_lifetime, "lifetime")

    def _build_pie(self, chart_view: QChartView, detail: list[AppPeriodStat],
                   total: int, key: str):
        title = "焦点时长占比" if key == "focus" else "运行时长占比"
        chart = QChart()
        chart.setTitle(title)
        chart.setAnimationOptions(QChart.SeriesAnimations)

        if not detail or total <= 0:
            chart.setTitle("暂无数据")
            chart_view.setChart(chart)
            return

        series = QPieSeries()
        top_n = 12
        sorted_detail = sorted(
            detail,
            key=lambda x: x.focus_seconds if key == "focus" else x.lifetime_seconds,
            reverse=True,
        )
        shown = sorted_detail[:top_n]
        other = sum(
            d.focus_seconds if key == "focus" else d.lifetime_seconds
            for d in sorted_detail[top_n:]
        )

        for i, app_stat in enumerate(shown):
            label = f"{i+1}. {app_stat.app_name}"
            value = app_stat.focus_seconds if key == "focus" else app_stat.lifetime_seconds
            slice_ = series.append(label, value)
            slice_.setLabelVisible(True)
            slice_.setLabel(f"{label}\n{value/3600:.1f}h ({value/total*100:.1f}%)")

        if other > 0:
            slice_other = series.append("其他", other)
            slice_other.setLabelVisible(True)
            slice_other.setLabel(f"其他\n{other/3600:.1f}h ({other/total*100:.1f}%)")

        chart.addSeries(series)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignRight)

        chart_view.setChart(chart)
