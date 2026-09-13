"""设置页「恢复默认设置」：重置普通项，不动数据目录。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.window import Mywindow
from ui.settings import SettingsDialog
from util.config import Settings

_common.patch_heavy(Mywindow)
_common.ensure_db()

app = QApplication(sys.argv)
s = Settings()

CUSTOM_DIR = r"C:\some\custom\path"

# 设为非默认
s.set("closeToTray", "exit")
s.set("minimizeOnStart", True)
s.set("syncEnabled", False)
s.set("syncIntervalSeconds", 120)
s.set("idleEnabled", False)
s.set("idleThresholdSeconds", 900)
s.set("idleTipEnabled", True)
s.set("hideWindowOnPick", False)
s.set("showTrayIcon", False)
s.set("cloudSaveEnabled", False)
s.set("cloudSyncOnLogin", True)
s.set("cloudAutoUploadOnClose", True)
s.set("useSystemProxy", True)
s.set("themeMode", "dark")
s.set("timeFormat", "chinese")
s.set("tableZoom", 150)
s.set("dataDirectory", CUSTOM_DIR)

win = Mywindow()
win.show()
app.processEvents()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

dlg = SettingsDialog(win, win._app_start_time, 0)
check("存在恢复默认按钮", dlg.btn_reset.text() == "恢复默认设置")
dlg._on_reset_defaults()
app.processEvents()

check("closeToTray -> None", s.get("closeToTray") is None)
check("minimizeOnStart -> False", s.get("minimizeOnStart") is False)
check("syncEnabled -> True", s.get("syncEnabled") is True)
check("syncIntervalSeconds -> 60", s.get("syncIntervalSeconds") == 60)
check("idleEnabled -> True", s.get("idleEnabled") is True)
check("idleThresholdSeconds -> 300", s.get("idleThresholdSeconds") == 300)
check("idleTipEnabled -> False", s.get("idleTipEnabled") is False)
check("hideWindowOnPick -> True", s.get("hideWindowOnPick") is True)
check("showTrayIcon -> True", s.get("showTrayIcon") is True)
check("cloudSaveEnabled -> True", s.get("cloudSaveEnabled") is True)
check("cloudSyncOnLogin -> False", s.get("cloudSyncOnLogin") is False)
check("cloudAutoUploadOnClose -> False", s.get("cloudAutoUploadOnClose") is False)
check("useSystemProxy -> False", s.get("useSystemProxy") is False)
check("themeMode -> system", s.get("themeMode") == "system")
check("timeFormat -> english", s.get("timeFormat") == "english")
check("tableZoom -> 100", s.get("tableZoom") == 100)
check("dataDirectory 未被重置", s.get("dataDirectory") == CUSTOM_DIR)

dlg.deleteLater()
win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
