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

# 文案对齐与 tooltip
check("按钮: 从云端导入…", dlg.btn_from_cloud.text() == "从云端导入…")
check("按钮: 下载到本地(无省略号)", dlg.btn_download.text() == "下载到本地")
check("按钮: 解除云端关联", dlg.btn_unbind.text() == "解除云端关联")
check("按钮: 新建目录", dlg.btn_add.text() == "新建目录")
check("按钮: 删除目录", dlg.btn_del_local.text() == "删除目录")
check("按钮: 编辑条目", dlg.btn_edit.text() == "编辑条目")
check("按钮: 删除存档位…", dlg.btn_del_slot.text() == "删除存档位…")
_btns = (dlg.btn_from_cloud, dlg.btn_add, dlg.btn_edit, dlg.btn_upload, dlg.btn_download,
         dlg.btn_view, dlg.btn_del_slot, dlg.btn_unbind, dlg.btn_del_remote, dlg.btn_del_local)
check("10 个按钮均有 tooltip", all(b.toolTip() for b in _btns))
check("表头用语对齐",
      [dlg.table.horizontalHeaderItem(c).text() for c in range(5)]
      == ["名称", "存档目录", "云端版本", "状态", "关联应用"])
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

# --- 新增云存档：关联应用选择窗口 + 名称预填 ---
from ui.personal_center import AddSaveGameDialog, AppPickDialog  # noqa: E402

AppRepository.add_app(r"C:\games\TestApp.exe", "TestApp")

ap = AppPickDialog(None)
rows = {ap.table.item(r, 0).text() for r in range(ap.table.rowCount())}
check("AppPick 列出已监控应用", "TestApp" in rows)
ap.search_edit.setText("TestApp")
check("AppPick 搜索过滤", ap.table.rowCount() == 1)
ap.table.selectRow(0)
sel = ap.selected_app()
check("AppPick 返回所选应用", sel is not None and sel.exe_name == "TestApp")
ap.close()

ad = AddSaveGameDialog(None)
ad._apply_app(r"C:\games\TestApp.exe", "TestApp")
check("选应用后名称预填", ad.name_edit.text() == "TestApp")
check("标识符随名称默认生成", ad.identifier_edit.text() == "TestApp")
ad.name_edit.setText("我的自定义名")
ad._on_name_edited("我的自定义名")  # 模拟用户手改
check("改名后标识符联动", ad.identifier_edit.text() == "我的自定义名")
ad._apply_app(r"C:\games\Other.exe", "Other")
check("手改名称后换应用不覆盖", ad.name_edit.text() == "我的自定义名")
check("values 返回关联路径与标识符",
      ad.values()["linked_app_path"] == r"C:\games\Other.exe"
      and ad.values()["identifier"] == "我的自定义名")
ad._clear_app()
check("清除关联", ad.values()["linked_app_path"] is None and ad.app_edit.text() == "")
ad.close()

# 手改标识符后，改名称不再覆盖标识符
ad_id = AddSaveGameDialog(None)
ad_id.name_edit.setText("游戏A")
ad_id._on_name_edited("游戏A")
ad_id.identifier_edit.setText("game-a")
ad_id._on_identifier_edited("game-a")
ad_id.name_edit.setText("游戏B")
ad_id._on_name_edited("游戏B")
check("手改标识符后不再联动", ad_id.identifier_edit.text() == "game-a")
ad_id.close()

# 中文名称允许直接作为标识符；冲突标识符被拦截
ad_cn = AddSaveGameDialog(None)
ad_cn.name_edit.setText("艾尔登法环")
ad_cn._on_name_edited("艾尔登法环")
check("中文可作标识符", ad_cn.identifier_edit.text() == "艾尔登法环")
ad_cn.close()

import _common  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

ad_dup = AddSaveGameDialog(None, taken_identifiers={"taken"})
ad_dup.name_edit.setText("X")
ad_dup._on_name_edited("X")
ad_dup.identifier_edit.setText("taken")
ad_dup._on_identifier_edited("taken")
ad_dup.dir_edit.setText(_common.tmpdir("pc_dir_"))
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
ad_dup._on_ok()
check("标识符与本地条目重复被拦截", ad_dup.result() != QDialog.Accepted)
ad_dup.close()

# 编辑态预填
e_edit = AppRepository.create_save_game("原标题", r"C:\orig", None, "orig-id")
ad_ed = AddSaveGameDialog(None, entry=e_edit)
check("编辑态预填名称/标识符/目录",
      ad_ed.name_edit.text() == "原标题" and ad_ed.identifier_edit.text() == "orig-id"
      and ad_ed.dir_edit.text() == r"C:\orig")
ad_ed.close()

# 编辑落库（本地直改）
d_edit = PersonalCenter(None, "token", "tester")
d_edit._apply_edit(e_edit, {"name": "改后", "identifier": "new-id",
                            "local_path": r"C:\new", "linked_app_path": None})
g_edit = AppRepository.get_save_game(e_edit.id)
check("编辑写入本地库",
      g_edit.name == "改后" and g_edit.identifier == "new-id" and g_edit.local_path == r"C:\new")
AppRepository.delete_save_game(e_edit.id)

# 删除存档位回调：若条目正绑定该槽则清记录
e_slot = AppRepository.create_save_game("槽位游戏", r"C:\slot", None, "slot-id")
AppRepository.set_save_game_server_id(e_slot.id, 5)
AppRepository.set_save_game_slot(e_slot.id, 2)
e_slot = AppRepository.get_save_game(e_slot.id)  # 重新取（含 server_slot）
d_edit._pending_delete_slot = (e_slot, 2)
d_edit._on_delete_slot_done(True, {"slot": 2})
g_slot = AppRepository.get_save_game(e_slot.id)
check("删除槽位后清空绑定槽记录", g_slot.server_slot is None and g_slot.last_synced_version is None)
AppRepository.delete_save_game(e_slot.id)
d_edit.close()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
