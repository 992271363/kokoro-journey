"""FirstRunWizard：首次显示默认路径；重新配置显示当前路径并区分标题/按钮；
并拒绝把数据目录设为程序配置目录本身。"""
import _common  # noqa: F401

import os
import sys
import tempfile

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ui.wizard import FirstRunWizard
from util.config import Settings
from util.path import _default_appdata, _settings_dir

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

# 边界：拒绝把数据目录设为程序配置目录本身
warnings = []
_orig_warning = QMessageBox.warning
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[2] if len(a) > 2 else ""))

Settings().set("dataDirectory", "ORIGINAL")
w3 = FirstRunWizard(initial_path=_settings_dir(), reconfigure=True)
w3._confirm()
check("配置目录本身: 弹出拒绝警告", len(warnings) == 1)
check("配置目录本身: 未接受", w3.result() != QDialog.Accepted)
check("配置目录本身: dataDirectory 未被改写", Settings().get("dataDirectory") == "ORIGINAL")

# 对照：普通目录应能正常确认
warnings.clear()
good = tempfile.mkdtemp(prefix="kokoro_wizard_ok_")
w4 = FirstRunWizard(initial_path=good, reconfigure=True)
w4._confirm()
check("普通目录: 无警告", len(warnings) == 0)
check("普通目录: 已接受", w4.result() == QDialog.Accepted)
check("普通目录: dataDirectory 已更新",
      os.path.normcase(Settings().get("dataDirectory")) == os.path.normcase(os.path.normpath(good)))
QMessageBox.warning = _orig_warning

w1.deleteLater()
w2.deleteLater()
w3.deleteLater()
w4.deleteLater()
app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
