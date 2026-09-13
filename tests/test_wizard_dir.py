"""FirstRunWizard：首次显示默认路径；重新配置显示当前路径并区分标题/按钮。"""
import _common  # noqa: F401

import os
import sys

from PySide6.QtWidgets import QApplication

from ui.wizard import FirstRunWizard
from util.path import _default_appdata

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# 首次运行：默认路径 + 欢迎标题 + “开始使用”
w1 = FirstRunWizard()
check("首次: 显示默认路径", os.path.normcase(w1.selected_path()) == os.path.normcase(_default_appdata()))
check("首次: 标题为欢迎", w1.windowTitle() == "欢迎使用 Kokoro Journey")
check("首次: 按钮为开始使用", w1.confirm_btn.text() == "开始使用")
check("首次: reconfigure=False", w1._reconfigure is False)

# 重新配置：当前路径 + 更改标题 + “保存”
custom = os.path.join(os.path.expanduser("~"), "custom_data_dir")
w2 = FirstRunWizard(initial_path=custom, reconfigure=True)
check("重配: 显示当前路径", os.path.normcase(w2.selected_path()) == os.path.normcase(os.path.normpath(custom)))
check("重配: 路径框文本一致", w2.path_edit.text() == os.path.normpath(custom))
check("重配: 标题为更改", w2.windowTitle() == "更改数据存储位置")
check("重配: 按钮为保存", w2.confirm_btn.text() == "保存")
check("重配: reconfigure=True", w2._reconfigure is True)

w1.deleteLater()
w2.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
