"""Ctrl+= / Ctrl+- / Ctrl+0 缩放：主窗口焦点时生效、限幅 75~200、事件被消费。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent

from ui.window import Mywindow
from util.config import Settings

_common.patch_heavy(Mywindow)
_common.ensure_db()
Mywindow._refresh_table = lambda self, skip_width_hint=False, preserve_sort=False: None

app = QApplication(sys.argv)
_settings = Settings()
_orig_zoom = _settings.get("tableZoom", 100)

applied = []


class FakeTableManager:
    def apply_zoom(self, factor):
        applied.append(factor)

    def refresh(self, *a, **k):
        pass


def make_key(target, key, ctrl=True, shift=False):
    modifiers = Qt.NoModifier
    if ctrl:
        modifiers |= Qt.ControlModifier
    if shift:
        modifiers |= Qt.ShiftModifier
    ev = QKeyEvent(QEvent.Type.KeyPress, key, modifiers)
    app.sendEvent(target, ev)
    return ev


ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def reset_zoom(value):
    applied.clear()
    _settings.set("tableZoom", value)


win = Mywindow()
win.show()
app.processEvents()
win.table_manager = FakeTableManager()
viewport = win.tableWidget.viewport()

reset_zoom(100)
ev = make_key(viewport, Qt.Key_Equal)
check("Ctrl+= 放大一格 100->105", _settings.get("tableZoom") == 105)
check("live 应用 1.05", applied == [1.05])
check("事件被消费", ev.isAccepted())

reset_zoom(100)
make_key(viewport, Qt.Key_Plus, shift=True)
check("Ctrl+Shift+=（+号）放大 100->105", _settings.get("tableZoom") == 105)

reset_zoom(100)
make_key(viewport, Qt.Key_Plus)
check("小键盘 + 放大 100->105", _settings.get("tableZoom") == 105)

reset_zoom(100)
make_key(viewport, Qt.Key_Minus)
check("Ctrl+- 缩小 100->95", _settings.get("tableZoom") == 95)

reset_zoom(100)
make_key(viewport, Qt.Key_Underscore, shift=True)
check("Ctrl+Shift+-（下划线）缩小 100->95", _settings.get("tableZoom") == 95)

reset_zoom(150)
make_key(viewport, Qt.Key_0)
check("Ctrl+0 恢复 100", _settings.get("tableZoom") == 100 and applied == [1.0])

reset_zoom(200)
make_key(viewport, Qt.Key_Equal)
check("上限 200 不再增长", _settings.get("tableZoom") == 200 and not applied)

reset_zoom(75)
make_key(viewport, Qt.Key_Minus)
check("下限 75 不再降低", _settings.get("tableZoom") == 75 and not applied)

reset_zoom(100)
ev = make_key(viewport, Qt.Key_Equal, ctrl=False)
check("无 Ctrl 不缩放", _settings.get("tableZoom") == 100 and not applied)
check("无 Ctrl 事件不消费", not ev.isAccepted())

reset_zoom(100)
other = QWidget()
other.resize(200, 100)
other.show()
app.processEvents()
make_key(other, Qt.Key_Equal)
check("窗口外不缩放", _settings.get("tableZoom") == 100 and not applied)
other.close()

_settings.set("tableZoom", _orig_zoom)
win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
