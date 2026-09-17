"""窗口状态：保存/恢复几何与状态、版本号全屏留白。"""
import _common  # noqa: F401

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

from ui.window import Mywindow
from util.config import Settings
from db.repository import AppRepository

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
win.setGeometry(150, 110, 1020, 620)
app.processEvents()
win._save_window_state()
geo = s.get("windowGeometry")
check("保存普通几何", geo == {"x": 150, "y": 110, "width": 1020, "height": 620})
check("保存普通状态", s.get("windowState") == "normal")

# --- 状态列表头：留空（靠图标），带 tooltip ---
hdr0 = win.tableWidget.horizontalHeaderItem(0)
check("状态列表头留空", hdr0 is not None and hdr0.text() == "")
check("状态列表头带 tooltip", hdr0 is not None and bool(hdr0.toolTip()))

# --- 账号入口：按钮 + 下拉菜单 ---
check("账号按钮初始为登录", win.account_button.text() == "登录")
_menu_items = [a.text() for a in win._account_menu.actions() if not a.isSeparator()]
check("账号菜单项", _menu_items == ["云存档…", "用户中心…", "退出登录"])
check("用户中心占位禁用", not win.act_user_center.isEnabled())
win.run_immediate_sync = lambda: None
win._maybe_cloud_sync_on_login = lambda: None
win._apply_login_success("tok", "alice")
check("登录后按钮显示用户名", win.account_button.text() == "alice ▾")
check("登录后按钮 logged=true", win.account_button.property("logged") is True)
win._logout()
check("退出后按钮回到登录", win.account_button.text() == "登录")
check("退出后按钮 logged=false", win.account_button.property("logged") is False)

# --- 工具栏：800×600 主控件全可见 + 原生扩展按钮仅作最后一级 ---
check("窗口最小尺寸 800×600",
      win.minimumSize().width() == 800 and win.minimumSize().height() == 600)

_main_controls = (win.btn_monitor_toggle, win.pushButton_procs, win.btn_crosshair,
                  win.search_edit, win.btn_stats, win.btn_analysis,
                  win.account_button, win.settings_button)


def _settle():
    for _ in range(3):
        app.processEvents()


win.resize(800, 600)
_settle()
check("800×600 主控件全部可见", all(w.isVisible() for w in _main_controls))

for i in range(12):
    AppRepository.create_group(f"t小组{i}")
win._rebuild_group_buttons()
win.resize(800, 600)
_settle()
check("多分组 800×600 主控件仍可见", all(w.isVisible() for w in _main_controls))
check("分组溢出进入「…」",
      win._btn_group_overflow.isVisible() and len(win._hidden_group_buttons) > 0)

win.setMinimumSize(0, 0)
win.resize(520, 600)
_settle()
_ext = next((b for b in win._toolbar.findChildren(QToolButton)
             if "Extension" in b.metaObject().className()), None)
check("真溢出时扩展按钮可见", _ext is not None and _ext.isVisible())
if _ext is not None:
    check("扩展按钮为显式主题箭头",
          _ext.arrowType() == Qt.NoArrow and not _ext.icon().isNull()
          and _ext.toolTip() == "更多")
win.setMinimumSize(800, 600)
win.resize(800, 600)
_settle()

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
_mw = win2.minimumSize().width()
_mh = win2.minimumSize().height()
exp = (max(0, min(130, scr.width() - 100)),
       max(0, min(90, scr.height() - 100)),
       max(_mw, min(1000, scr.width())),
       max(_mh, min(560, scr.height())))
g = win2.geometry()
check("frozen 恢复几何", (g.x(), g.y(), g.width(), g.height()) == exp)

win2.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
