"""启动流程：需要 LE 但未绑定/失败时不启动并提示；不需要 LE 时普通启动。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication

from ui.window import Mywindow
from util.config import Settings
from util import le
from db.repository import AppRepository

_common.patch_heavy(Mywindow)
_common.ensure_db()
Mywindow._refresh_table = lambda self, skip_width_hint=False, preserve_sort=False: None

app = QApplication(sys.argv)
settings = Settings()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


win = Mywindow()
calls = []
win._launch_normal = lambda target: calls.append(("normal", target))
win._notify_le_problem = lambda reason: calls.append(("notify", reason))

plain = r"c:\games\plain.exe"
le_app_path = r"c:\games\le.exe"
AppRepository.add_app(plain, "plain.exe")
AppRepository.add_app(le_app_path, "le.exe")
AppRepository.set_launch_with_le(le_app_path, True)

settings.set("leRootDir", "")
settings.set("leProfileGuid", "")

# 1) 不需要 LE → 普通启动
calls.clear()
win._on_launch_requested(plain, False)
check("普通应用 → 普通启动", calls == [("normal", plain)])

# 2) 勾了 LE 但未绑定 → 不启动，只提示
calls.clear()
win._on_launch_requested(le_app_path, False)
check("勾了 LE 但未绑定 → 提示且不启动",
      len(calls) == 1 and calls[0][0] == "notify")

# 3) 未绑定 + 一次性强制 → 同样提示且不启动
calls.clear()
win._on_launch_requested(plain, True)
check("强制 LE 但未绑定 → 提示且不启动",
      len(calls) == 1 and calls[0][0] == "notify")

# 4) 绑定且可用 → 走 LE
_orig_ready, _orig_launch = le.check_ready, le.launch_with_le
le.check_ready = lambda root, guid: (True, "")
le.launch_with_le = lambda leproc, guid, target: (calls.append(("le", target)) or (True, ""))
settings.set("leRootDir", r"D:\LE")
settings.set("leProfileGuid", "8c9d8552-f076-4491-9f1c-9d2de66786a6")
calls.clear()
win._on_launch_requested(le_app_path, False)
check("绑定后 → 走 LE", calls == [("le", le_app_path)])

# 5) 绑定但启动失败 → 不回退普通启动，只提示
le.launch_with_le = lambda leproc, guid, target: (False, "启动失败")
calls.clear()
win._on_launch_requested(le_app_path, False)
check("LE 启动失败 → 不回退、只提示",
      len(calls) == 1 and calls[0][0] == "notify")

le.check_ready, le.launch_with_le = _orig_ready, _orig_launch
settings.set("leRootDir", "")
settings.set("leProfileGuid", "")
AppRepository.delete_app_completely(plain)
AppRepository.delete_app_completely(le_app_path)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
