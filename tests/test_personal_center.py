"""个人中心云存档管理：离屏构建 + 本地条目/状态渲染（云端调用被打桩，不联网）。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication

import core.save_sync as ss
from db.repository import AppRepository

_common.ensure_db()

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# 打桩云端调用，避免联网
ss.claim_device = lambda token: (True, {"activeDeviceId": "dev", "previousDeviceId": None})
ss.list_games = lambda token: (True, [])

from ui.personal_center import PersonalCenter  # noqa: E402

# 空列表
dlg = PersonalCenter(None, "token", "tester")
check("空列表无行", dlg.table.rowCount() == 0)
dlg.close()

# 本地条目 -> 状态为“尚未上传”
obj = AppRepository.create_save_game("G1", r"C:\not_exist_dir_xyz", None)
dlg2 = PersonalCenter(None, "token", "tester")
check("有 1 条本地条目", dlg2.table.rowCount() == 1)
check("状态为尚未上传", dlg2.table.item(0, 3).text() == "尚未上传")
check("云端最新为占位", dlg2.table.item(0, 2).text() == "—")
dlg2.close()

AppRepository.delete_save_game(obj.id)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
