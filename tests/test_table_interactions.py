"""主界面列表交互：双击动作分发 / 重命名期间忽略 / LE 一次性入口的显示条件。"""
import _common  # noqa: F401

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from db.repository import AppInfo
from ui.table import AppTableManager, should_offer_le_launch
from util.config import Settings

app = QApplication(sys.argv)
settings = Settings()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def make_app(path: str, with_le: bool = False) -> AppInfo:
    return AppInfo(
        exe_path=path,
        launch_path=path,
        exe_name=Path(path).name,
        total_focus_seconds=0,
        total_lifetime_seconds=0,
        last_start_at="",
        first_seen_at="",
        launch_with_le=with_le,
    )


table = QTableWidget()
manager = AppTableManager(table, None, settings)

apps = [make_app(r"c:\games\a.exe", with_le=False), make_app(r"c:\games\b.exe", with_le=True)]
table.setRowCount(len(apps))
for row, info in enumerate(apps):
    item = QTableWidgetItem(Path(info.exe_name).stem)
    item.setData(Qt.UserRole, info.exe_path)
    table.setItem(row, 2, item)
manager._last_apps = apps

events = []
manager.detail_requested.connect(lambda path: events.append(("detail", path)))
manager.launch_requested.connect(lambda path, force: events.append(("launch", path, force)))

model = table.model()


def dbl(row: int):
    events.clear()
    manager._on_double_clicked(model.index(row, 2))


# 默认：双击 = 启动游戏
settings.set("tableDoubleClickAction", "launch")
dbl(0)
check("默认双击 → 启动", events == [("launch", r"c:\games\a.exe", False)])

# 设置为查看详情
settings.set("tableDoubleClickAction", "detail")
dbl(1)
check("切到详情 → 打开详情", events == [("detail", r"c:\games\b.exe")])

# 重命名进行中：双击不触发
settings.set("tableDoubleClickAction", "launch")
manager._editing_rename = True
dbl(0)
check("重命名进行中双击被忽略", events == [])
manager._editing_rename = False

# 另一个应用（勾了 LE）也能正常分发
dbl(1)
check("第二行也能启动", events == [("launch", r"c:\games\b.exe", False)])

# 找不到路径的行：不触发
empty_row = table.rowCount()
table.setRowCount(empty_row + 1)
events.clear()
manager._on_double_clicked(model.index(empty_row, 2))
check("空行不触发", events == [])

# LE 一次性入口的显示条件：已勾选则不再提供
check("未勾选 LE → 提供一次性入口", should_offer_le_launch(False) is True)
check("已勾选 LE → 不提供一次性入口", should_offer_le_launch(True) is False)
check("按路径取到应用信息", manager._app_for_path(r"c:\games\b.exe").launch_with_le is True)

settings.set("tableDoubleClickAction", "launch")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
