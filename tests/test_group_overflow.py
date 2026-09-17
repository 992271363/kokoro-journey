"""分组溢出：过多分组收进「...」、选中折叠项高亮显示全名、长名省略。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.window import Mywindow, GroupChipButton
from db.repository import AppRepository

_common.patch_heavy(Mywindow)
_common.ensure_db()
Mywindow._refresh_table = lambda self, skip_width_hint=False, preserve_sort=False: None

FAKE = []
AppRepository.get_all_groups = staticmethod(lambda: list(FAKE))

app = QApplication(sys.argv)
win = Mywindow()
win.show()
app.processEvents()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def pump():
    app.processEvents()
    app.processEvents()


def set_groups(items):
    FAKE.clear()
    FAKE.extend(items)


def chip_by_gid(gid):
    for b in win.group_buttons.buttons():
        if b.property("group_id") == gid:
            return b
    return None


# --- 过多分组：窄窗口折叠 ---
set_groups([(i + 1, f"分组{i + 1}", None) for i in range(15)])
win._rebuild_group_buttons()
win.resize(820, 675)
pump()
check("窄窗口有折叠项", len(win._hidden_group_buttons) > 0)
check("窄窗口显示「...」", win._btn_group_overflow.isVisible())

win.resize(2000, 675)
pump()
check("宽窗口无折叠项", len(win._hidden_group_buttons) == 0)
check("宽窗口隐藏「...」", not win._btn_group_overflow.isVisible())

# --- 选中被折叠的分组：高亮 + 显示全名 ---
win.resize(820, 675)
win._rebuild_group_buttons()
pump()
target = win._hidden_group_buttons[0]
gid = target.property("group_id")
full = win._find_group_name(gid)
win._select_group_button(target)
pump()
check("选中折叠分组生效", win._current_group_id == gid)
check("「...」高亮", win._btn_group_overflow.isChecked())
check("「...」显示完整分组名", win._btn_group_overflow.text() == full)

# --- 长名称：不截断、不省略、无固定上限、左对齐 ---
long_name = "这是一个非常非常长的分组名称用于测试省略效果"
set_groups([(1, long_name, None)])
win._rebuild_group_buttons()
pump()
btn = chip_by_gid(1)
check("长名称完整保留", btn.text() == long_name and "…" not in btn.text())
check("tooltip 保留全名", btn.toolTip() == long_name)
check("chip 无固定宽度上限", btn.maximumWidth() == 16777215)
check("chip 宽度足够显示全名",
      btn.minimumSizeHint().width() >= btn.fontMetrics().horizontalAdvance(long_name))
check("chip 文本左对齐", btn.property("group_chip") is True)
check("分组按钮可键盘聚焦", btn.focusPolicy() != Qt.NoFocus)
check("「...」可键盘聚焦", win._btn_group_overflow.focusPolicy() != Qt.NoFocus)

win.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
