"""分组删除：右键菜单危险项为红色、左键触发；删除前必须确认（默认「否」）。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import (
    QApplication, QMenu, QMessageBox, QWidgetAction, QPushButton,
)

from ui.window import Mywindow
from db.repository import AppRepository

_common.patch_heavy(Mywindow)
_common.ensure_db()

FAKE = [(7, "游戏", "#60a5fa")]
AppRepository.get_all_groups = staticmethod(lambda: list(FAKE))
deleted = []
AppRepository.delete_group = staticmethod(lambda gid: deleted.append(gid))

app = QApplication(sys.argv)
win = Mywindow()
win.show()
app.processEvents()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# --- 危险菜单项：红色 + 左键触发 ---
menu = QMenu(win)
ran = []
win._add_danger_menu_action(menu, "删除分组...", lambda: ran.append(True))
wa = [a for a in menu.actions() if isinstance(a, QWidgetAction)][0]
btn = wa.defaultWidget()
check("危险项是按钮", isinstance(btn, QPushButton))
check("危险项文本", btn.text() == "删除分组...")
check("危险项为红色", "#ef4444" in btn.styleSheet())
btn.click()
app.processEvents()
check("左键触发槽", ran == [True])

# --- 确认门禁 ---
captured = {}


def fake_question(parent, title, text, buttons=None, defaultButton=None):
    captured["default"] = defaultButton
    captured["text"] = text
    return captured["ret"]


orig_q = QMessageBox.question
QMessageBox.question = staticmethod(fake_question)

captured["ret"] = QMessageBox.No
win._delete_group(7)
check("确认框默认按钮为「否」", captured["default"] == QMessageBox.No)
check("选择「否」不删除", deleted == [])

captured["ret"] = QMessageBox.Yes
win._delete_group(7)
check("选择「是」执行删除", deleted == [7])

QMessageBox.question = orig_q
win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
