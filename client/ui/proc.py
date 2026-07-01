from PySide6.QtCore import Qt  # Qt 基础枚举/常量
from PySide6.QtWidgets import (
    QDialog, QTableWidget, QTableWidgetItem, QPushButton, QLineEdit,
    QLabel, QVBoxLayout, QHBoxLayout, QSpacerItem, QSizePolicy,
    QHeaderView, QAbstractItemView
)  # 批量导入所需控件和布局类

from core.monitor import get_process_list  # 进程列表数据源
from util.search import make_search_keywords, matches_search_keywords


class ProcSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("进程列表")
        self.resize(564, 429)
        self.proc_pid = None  # 预留进程 PID（当前未使用）

        # ---- 纯代码 UI 初始化（原 Ui_ProcListDialog.py 逻辑内联）----
        self.verticalLayout = QVBoxLayout(self)  # 主垂直布局

        self.procTable = QTableWidget()  # 进程表格
        self.procTable.setColumnCount(3)
        self.procTable.setHorizontalHeaderLabels(["PID", "进程名", "进程路径"])
        self.verticalLayout.addWidget(self.procTable)

        self.horizontalLayout_2 = QHBoxLayout()  # 工具栏行
        self.list_brush = QPushButton("刷新")  # 刷新按钮
        self.horizontalLayout_2.addWidget(self.list_brush)
        self.horizontalLayout_2.addSpacerItem(
            QSpacerItem(34, 14, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )  # 水平弹簧，把搜索框顶到右边
        self.lineEdit_search = QLineEdit()  # 搜索输入框
        self.lineEdit_search.setMaximumSize(155, 16777215)  # 限制宽度
        self.lineEdit_search.setAlignment(Qt.AlignCenter)  # 文字居中
        self.lineEdit_search.setPlaceholderText("搜索")
        self.horizontalLayout_2.addWidget(self.lineEdit_search)
        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.horizontalLayout = QHBoxLayout()  # 底部操作栏
        self.label = QLabel("过长的值可以悬浮鼠标显示")  # 提示标签
        self.horizontalLayout.addWidget(self.label)
        self.horizontalLayout.addSpacerItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )  # 弹簧，把按钮组顶到右边
        self.pushButton_accept = QPushButton("确认")  # 确认按钮
        self.pushButton_reject = QPushButton("取消")  # 取消按钮
        self.pushButton_reject.setProperty("secondary", True)  # 标记为次要样式
        self.horizontalLayout.addWidget(self.pushButton_accept)
        self.horizontalLayout.addWidget(self.pushButton_reject)
        self.verticalLayout.addLayout(self.horizontalLayout)
        # ---------------------------------------------------------------

        # 信号连接：搜索文本变化或点击刷新时重新加载进程列表
        self.lineEdit_search.textChanged.connect(self.populate_process_list)
        self.list_brush.clicked.connect(self.populate_process_list)

        # 表格列宽策略：PID 列自适应内容，进程名列可手动拖动，路径列自动填充
        header = self.procTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        self.procTable.setSortingEnabled(True)  # 允许点击表头排序
        self.procTable.setSelectionBehavior(QAbstractItemView.SelectRows)  # 整行选中
        self.procTable.setSelectionMode(QAbstractItemView.SingleSelection)  # 单行选择
        self.procTable.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 禁止编辑单元格
        self.procTable.setAlternatingRowColors(True)  # 交替行背景色

        # 确认/取消按钮行为
        self.pushButton_accept.clicked.connect(self.accept)  # QDialog 的 accept
        self.pushButton_reject.clicked.connect(self.reject)  # QDialog 的 reject

        self.populate_process_list()  # 初始加载进程数据

    def get_selected_proc_info(self):
        """返回选中进程的 (可执行路径, 进程名)，无选中时返回 None"""
        selected_rows_indexes = self.procTable.selectionModel().selectedRows()
        if not selected_rows_indexes:
            return None
        row = selected_rows_indexes[0].row()
        exe_name = self.procTable.item(row, 1).text()
        exe_path = self.procTable.item(row, 2).text()
        return (exe_path, exe_name)

    def populate_process_list(self):
        """根据搜索词过滤并重新填充进程表格"""
        keywords = make_search_keywords(self.lineEdit_search.text())

        self.procTable.setSortingEnabled(False)  # 数据更新时先关闭排序，避免索引错乱
        self.procTable.setRowCount(0)  # 清空表格

        processes = get_process_list()  # 获取所有进程

        # 无搜索词则显示全部，否则按关键词匹配 PID/名称/路径
        if not keywords:
            filtered_processes = processes
        else:
            filtered_processes = [
                proc for proc in processes
                if matches_search_keywords(
                    [proc['pid'], proc['name'], proc['exe'] or ""], keywords
                )
            ]

        # 填充表格并附加 tooltip，方便完整查看截断内容
        self.procTable.setRowCount(len(filtered_processes))
        for row, proc_info in enumerate(filtered_processes):
            # PID 列使用 DisplayRole 和 UserRole 分别存储显示值和真实数据
            pid_item = QTableWidgetItem()
            pid_item.setData(Qt.ItemDataRole.DisplayRole, proc_info['pid'])
            pid_item.setData(Qt.ItemDataRole.UserRole, proc_info['pid'])
            pid_item.setToolTip(str(proc_info['pid']))

            name_item = QTableWidgetItem(proc_info['name'])
            name_item.setToolTip(proc_info['name'])

            path_str = proc_info['exe'] or "N/A"
            path_item = QTableWidgetItem(path_str)
            path_item.setToolTip(path_str)

            self.procTable.setItem(row, 0, pid_item)
            self.procTable.setItem(row, 1, name_item)
            self.procTable.setItem(row, 2, path_item)

        self.procTable.setSortingEnabled(True)  # 数据填充完毕，重新开启排序
