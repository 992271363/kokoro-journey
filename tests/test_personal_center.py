"""个人中心云存档管理（P1+P4）：离屏构建、本地条目状态、云端弹窗、解除绑定。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

import core.save_sync as ss
from db.repository import AppRepository

_common.ensure_db()

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


CLOUD = [{"id": 5, "name": "CloudG", "latestVersion": 3,
          "latestTotalSize": 100, "latestFileCount": 2, "latestCreatedAt": None}]
NOVER = [{"id": 6, "name": "NoVer", "latestVersion": None,
          "latestTotalSize": 0, "latestFileCount": 0, "latestCreatedAt": None}]

ss.claim_device = lambda t: (True, {"activeDeviceId": "d", "previousDeviceId": None})
ss.list_games = lambda t: (True, [dict(x) for x in CLOUD])

from ui.personal_center import PersonalCenter, CloudGamesDialog  # noqa: E402

# 空本地
dlg = PersonalCenter(None, "token", "tester")
check("空列表无行", dlg.table.rowCount() == 0)
dlg.close()

# 云端弹窗：未关联
cd = CloudGamesDialog(None, {g["id"]: g for g in CLOUD}, [])
check("云端弹窗列出 1 个", cd.table.rowCount() == 1)
check("状态 未关联", cd.table.item(0, 3).text() == "未关联")
cd.close()

# 绑定同 id -> 已关联
g = AppRepository.create_save_game("CloudG", r"C:\x", None)
AppRepository.set_save_game_server_id(g.id, 5)
cd2 = CloudGamesDialog(None, {5: CLOUD[0]}, AppRepository.get_all_save_games())
check("状态 已关联", cd2.table.item(0, 3).text() == "已关联")
cd2.close()
AppRepository.delete_save_game(g.id)

# 绑定到已删除的云端 -> 状态「云端已删除」+ 解除绑定可用
g2 = AppRepository.create_save_game("Gone", r"C:\y", None)
AppRepository.set_save_game_server_id(g2.id, 99)
dlg2 = PersonalCenter(None, "token", "tester")
check("主表 1 行", dlg2.table.rowCount() == 1)
check("状态 云端已删除", dlg2.table.item(0, 3).text() == "云端已删除")
dlg2.table.selectRow(0)
check("解除绑定可用", dlg2.btn_unbind.isEnabled())
AppRepository.clear_save_game_server_id(g2.id)
check("解除后 server_id 为空", AppRepository.get_save_game(g2.id).server_id is None)
dlg2.close()
AppRepository.delete_save_game(g2.id)

# 云端暂无版本
ss.list_games = lambda t: (True, [dict(x) for x in NOVER])
g3 = AppRepository.create_save_game("NoVer", r"C:\z", None)
AppRepository.set_save_game_server_id(g3.id, 6)
ss.claim_device = lambda t: (True, {"activeDeviceId": "d", "previousDeviceId": None})
dlg3 = PersonalCenter(None, "token", "tester")
check("状态 云端暂无版本", dlg3.table.item(0, 3).text() == "云端暂无版本")
dlg3.close()
AppRepository.delete_save_game(g3.id)

# --- 409 被其他设备占用 -> 询问接管并重试上传（D1） ---
claimed = []
ss.claim_device = lambda t: (claimed.append(t) or (True, {"activeDeviceId": "d", "previousDeviceId": "x"}))
ss.list_games = lambda t: (True, [])

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

dlg4 = PersonalCenter(None, "token", "tester")
retried = []
dlg4._upload = lambda entry=None: retried.append(entry)

claimed.clear()  # 构造时 refresh() 已 claim 过一次，这里只统计后续
e_retry = AppRepository.create_save_game("RetryG", r"C:\r", None)
dlg4._pending_upload_entry = e_retry
dlg4._on_upload_done(False, ss.TAKEN_OVER)
check("409 接管后重试上传", len(claimed) == 1 and retried == [e_retry])

retried.clear()
claimed.clear()
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
dlg4._on_upload_done(False, ss.TAKEN_OVER)
check("拒绝接管则不重试", not retried and not claimed)

AppRepository.delete_save_game(e_retry.id)
dlg4.close()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
