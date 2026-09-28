"""C1：主表格空状态页（无应用 / 筛选无结果）。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication

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

# 构造“有应用但搜索无结果”（走真实的按数据搜索）
from db.repository import AppInfo  # noqa: E402


def _app(name: str) -> AppInfo:
    return AppInfo(
        exe_path=rf"c:\demo\{name}.exe",
        launch_path=rf"c:\demo\{name}.exe",
        exe_name=f"{name}.exe",
        total_focus_seconds=0,
        total_lifetime_seconds=0,
        last_start_at="",
        first_seen_at="",
    )


win.table_manager.refresh([_app("foobar"), _app("foobaz")])
win.search_edit.setText("zzz-no-match")
win._apply_table_search()
app.processEvents()
check("筛选无结果时仍在空状态页", win._table_stack.currentIndex() == 1)
check("筛选无结果文案正确", win._empty_title.text() == "未找到匹配的应用")
check("筛选无结果时隐藏添加按钮", not win._empty_add_btn.isVisible())

# 恢复匹配 -> 回到表格页
win.search_edit.setText("foobar")
win._apply_table_search()
app.processEvents()
check("有匹配时回到表格页", win._table_stack.currentIndex() == 0)

# 排序后搜索按“视觉行”过滤（回归）
from PySide6.QtCore import Qt  # noqa: E402


def _app_f(name: str, focus: int) -> AppInfo:
    a = _app(name)
    a.total_focus_seconds = focus
    return a


win.search_edit.setText("")
win.table_manager.refresh([_app_f("low", 10), _app_f("mid", 50), _app_f("high", 100)])
win.table_manager.sort_by_id("total_focus", Qt.DescendingOrder)
app.processEvents()
check("降序后视觉顺序为 high/mid/low",
      [win.table_manager.exe_path_at_row(r) for r in range(win.tableWidget.rowCount())]
      == [_app_f("high", 0).exe_path, _app_f("mid", 0).exe_path, _app_f("low", 0).exe_path])

win.search_edit.setText("high")
win._apply_table_search()
app.processEvents()
hidden = [win.tableWidget.isRowHidden(r) for r in range(win.tableWidget.rowCount())]
check("排序后搜索命中正确的视觉行", hidden == [False, True, True])

win.search_edit.setText("")
win._apply_table_search()
app.processEvents()

win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
