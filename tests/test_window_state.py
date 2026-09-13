"""窗口状态：保存/恢复几何与状态、版本号全屏留白。"""
import _common  # noqa: F401

import os
import sys

from PySide6.QtWidgets import QApplication

from ui.window import Mywindow
from util.config import Settings

_common.patch_heavy(Mywindow)
_common.ensure_db()

app = QApplication(sys.argv)
s = Settings()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# --- 保存：普通状态 ---
win = Mywindow()
win.show()
app.processEvents()
win._width_locked = True  # 阻止自动宽度调整，专注验证几何保存
win.setGeometry(150, 110, 1020, 580)
app.processEvents()
win._save_window_state()
geo = s.get("windowGeometry")
check("保存普通几何", geo == {"x": 150, "y": 110, "width": 1020, "height": 580})
check("保存普通状态", s.get("windowState") == "normal")

# --- 保存：最大化时记录“还原后”几何 ---
win.showMaximized()
app.processEvents()
normal = win.normalGeometry()
win._save_window_state()
check("最大化状态被记录", s.get("windowState") == "maximized")
saved = s.get("windowGeometry")
check("最大化时保存的是还原几何",
      saved["width"] == normal.width() and saved["height"] == normal.height())

# --- 版本号留白：全屏/最大化 8px，普通 0 ---
win.showNormal()
app.processEvents()
check("普通窗口版本号右边距 0", win._version_label.contentsMargins().right() == 0)
win.showMaximized()
app.processEvents()
check("最大化版本号右边距 8", win._version_label.contentsMargins().right() == 8)
win.showNormal()
app.processEvents()

# --- 恢复：frozen 模式按保存的几何恢复 ---
win.hide()
win.deleteLater()
app.processEvents()
s.set("windowGeometry", {"x": 130, "y": 90, "width": 1000, "height": 560})
s.set("windowState", "normal")
sys.frozen = True
sys._MEIPASS = _common._CLIENT  # 让 frozen 模式的资源路径指向真实 icons
win2 = Mywindow()
win2._width_locked = True
win2.show()
app.processEvents()
scr = win2.screen().availableGeometry()
exp = (max(0, min(130, scr.width() - 100)),
       max(0, min(90, scr.height() - 100)),
       min(1000, scr.width()),
       min(560, scr.height()))
g = win2.geometry()
check("frozen 恢复几何", (g.x(), g.y(), g.width(), g.height()) == exp)

win2.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
