"""C1：主表格空状态页（无应用 / 筛选无结果）。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QTableWidgetItem

from ui.window import Mywindow
from db.repository import AppRepository

_common.patch_heavy(Mywindow)
AppRepository.get_all_groups = staticmethod(lambda: [])
AppRepository.get_all_apps = staticmethod(lambda group_filter=None: [])
_common.ensure_db()

app = QApplication(sys.argv)
win = Mywindow()
win.show()
app.processEvents()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


win._refresh_table()
app.processEvents()
check("无应用时切到空状态页", win._table_stack.currentIndex() == 1)
check("无应用文案正确", win._empty_title.text() == "还没有监控的应用")
check("无应用时显示添加按钮", win._empty_add_btn.isVisible())

# 构造“有应用但搜索无结果”
win.tableWidget.setRowCount(2)
for r in range(2):
    for c in range(win.tableWidget.columnCount()):
        win.tableWidget.setItem(r, c, QTableWidgetItem("foo"))
win.search_edit.setText("zzz-no-match")
win._apply_table_search()
app.processEvents()
check("筛选无结果时仍在空状态页", win._table_stack.currentIndex() == 1)
check("筛选无结果文案正确", win._empty_title.text() == "未找到匹配的应用")
check("筛选无结果时隐藏添加按钮", not win._empty_add_btn.isVisible())

# 恢复匹配 -> 回到表格页
win.search_edit.setText("foo")
win._apply_table_search()
app.processEvents()
check("有匹配时回到表格页", win._table_stack.currentIndex() == 0)

win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
