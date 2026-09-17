"""设置页布局：左侧分类导航 + 右侧分页；控件仍可访问、切页不丢值、逻辑不变。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.window import Mywindow
from ui.settings import SettingsDialog
from util.config import Settings

_common.patch_heavy(Mywindow)
_common.ensure_db()

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


win = Mywindow()
win.show()
app.processEvents()

dlg = SettingsDialog(win, getattr(win, "_app_start_time", None), 0)
app.processEvents()

# --- 导航与分页 ---
nav_items = [dlg._nav.item(i).text() for i in range(dlg._nav.count())]
check("导航 4 项且顺序正确",
      nav_items == ["常规", "监控与同步", "云存档", "数据"])
check("分页数量与导航一致", dlg._stack.count() == 4)
check("默认选中第一页", dlg._nav.currentRow() == 0 and dlg._stack.currentIndex() == 0)


def on_page(index: int, widget) -> bool:
    page = dlg._stack.widget(index)
    return page is not None and widget is not None and page.isAncestorOf(widget)


# --- 每页包含预期控件（常规已并入原「外观」）---
check("常规页控件", all(on_page(0, w) for w in (
    dlg.combo_close_action, dlg.check_autostart,
    dlg.check_minimize_on_start, dlg.check_hide_on_pick,
    dlg.check_show_tray, dlg.radio_light, dlg.radio_dark, dlg.radio_system,
    dlg.radio_fmt_chinese, dlg.radio_fmt_english, dlg.radio_fmt_numeric,
    dlg.btn_zoom)))
check("监控与同步页控件", all(on_page(1, w) for w in (
    dlg.check_sync_enabled, dlg.spin_sync_interval,
    dlg.check_idle_enabled, dlg.spin_idle_threshold, dlg.check_idle_tip)))
check("云存档页控件", all(on_page(2, w) for w in (
    dlg.check_cloud_enabled, dlg.check_cloud_sync_login, dlg.check_cloud_auto_upload,
    dlg.check_cloud_use_proxy, dlg.proxy_address_edit, dlg.proxy_hint)))
check("数据页控件", all(on_page(3, w) for w in (
    dlg.path_edit, dlg.btn_change_dir, dlg.btn_data_transfer,
    dlg.btn_clear_data, dlg.btn_clear_failed,
    dlg._label_current, dlg._label_total)))

# --- 切页不丢已改值 ---
Settings().set("syncEnabled", True)
dlg._nav.setCurrentRow(1)
app.processEvents()
dlg.spin_sync_interval.setValue(123)
check("监控页已改值", dlg.spin_sync_interval.value() == 123)
dlg._nav.setCurrentRow(0)
app.processEvents()
dlg._nav.setCurrentRow(3)
app.processEvents()
dlg._nav.setCurrentRow(1)
app.processEvents()
check("切页后值保留", dlg.spin_sync_interval.value() == 123)
dlg.spin_sync_interval.setValue(60)

# --- 代理校验仍拦截保存 ---
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
dlg._nav.setCurrentRow(2)
app.processEvents()
dlg.check_cloud_use_proxy.setChecked(True)
dlg.proxy_address_edit.setText("127.0.0.1")
check("非法代理地址 保存被拦截", dlg._save_settings() is False)
dlg.proxy_address_edit.setText("127.0.0.1:7899")
check("合法代理地址 保存通过", dlg._save_settings() is True)
check("代理地址已落盘", Settings().get("proxyAddress") == "127.0.0.1:7899")

# --- 恢复默认仍全量生效 ---
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
dlg._on_reset_defaults()
check("重置后同步间隔回默认", Settings().get("syncIntervalSeconds") == 60)
check("重置后代理地址清空", Settings().get("proxyAddress") == "")
check("重置后 useSystemProxy=False", Settings().get("useSystemProxy") is False)

dlg.close()
win.close()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
