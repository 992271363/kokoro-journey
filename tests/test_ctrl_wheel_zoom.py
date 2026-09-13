"""Ctrl+滚轮缩放：主窗口焦点时生效、按刻度累积、限幅 75~200、事件被消费。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent

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


def make_wheel(target, delta_y, ctrl=True):
    modifiers = Qt.ControlModifier if ctrl else Qt.NoModifier
    ev = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10),
        QPoint(0, 0), QPoint(0, delta_y),
        Qt.NoButton, modifiers, Qt.ScrollUpdate, False,
    )
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
ev = make_wheel(viewport, 120)
check("Ctrl+wheel 上滚一格 100->105", _settings.get("tableZoom") == 105)
check("live 应用 1.05", applied == [1.05])
check("事件被消费", ev.isAccepted())

make_wheel(viewport, -120)
check("下滚一格 105->100", _settings.get("tableZoom") == 100)

reset_zoom(200)
make_wheel(viewport, 120)
check("上限 200 不再增长", _settings.get("tableZoom") == 200)

reset_zoom(75)
make_wheel(viewport, -120)
check("下限 75 不再降低", _settings.get("tableZoom") == 75)

reset_zoom(100)
make_wheel(viewport, 40)
make_wheel(viewport, 40)
check("触控板 80 未触发", _settings.get("tableZoom") == 100 and not applied)
make_wheel(viewport, 40)
check("累积 120 触发 100->105", _settings.get("tableZoom") == 105)

reset_zoom(100)
ev = make_wheel(viewport, 120, ctrl=False)
check("无 Ctrl 不缩放", _settings.get("tableZoom") == 100 and not applied)
check("无 Ctrl 事件不消费", not ev.isAccepted())

reset_zoom(100)
other = QWidget()
other.resize(200, 100)
other.show()
app.processEvents()
make_wheel(other, 120)
check("窗口外不缩放", _settings.get("tableZoom") == 100 and not applied)
other.close()

_settings.set("tableZoom", _orig_zoom)
win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
