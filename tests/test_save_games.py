"""云存档本地条目：建表 + repository CRUD + 同步状态更新（离屏、隔离数据目录）。"""
import _common  # noqa: F401

import sys

from db.repository import AppRepository

_common.ensure_db()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


obj = AppRepository.create_save_game("我的游戏", r"C:\saves\game1", r"C:\games\g1.exe")
check("创建本地条目", obj is not None and obj.id is not None and obj.name == "我的游戏")
check("未指定标识符时默认取名称", obj.identifier == "我的游戏")

items = AppRepository.get_all_save_games()
check("列表返回 1 条", len(items) == 1 and items[0].local_path == r"C:\saves\game1")

check("更新名称与标识符",
      AppRepository.update_save_game(obj.id, name="改名游戏", identifier="my-save"))
g1 = AppRepository.get_save_game(obj.id)
check("名称/标识符已更新", g1.name == "改名游戏" and g1.identifier == "my-save")

check("显式清空关联应用",
      AppRepository.update_save_game(obj.id, linked_app_path=None))
check("关联应用已清空", AppRepository.get_save_game(obj.id).linked_app_path is None)

check("单独的标识符创建",
      AppRepository.create_save_game("同名游戏", r"C:\saves\game2", None, "g2").identifier == "g2")
id_a = AppRepository.create_save_game("同名游戏", r"C:\saves\a", None, "ga").id
id_b = AppRepository.create_save_game("同名游戏", r"C:\saves\b", None, "gb").id
check("显示名称可重复",
      len([e for e in AppRepository.get_all_save_games() if e.name == "同名游戏"]) == 3)
AppRepository.delete_save_game(id_a)
AppRepository.delete_save_game(id_b)
_check_extra = AppRepository.get_all_save_games()
AppRepository.delete_save_game([e for e in _check_extra if e.identifier == "g2"][0].id)

check("写入 server_id", AppRepository.set_save_game_server_id(obj.id, 42))
check("写入同步状态", AppRepository.mark_save_game_synced(obj.id, 3, "fp123"))
g = AppRepository.get_save_game(obj.id)
check("同步状态已保存",
      g.server_id == 42 and g.last_synced_version == 3
      and g.local_fingerprint == "fp123" and g.last_synced_at is not None)

check("清空槽位记录", AppRepository.clear_save_game_slot(obj.id))
g2 = AppRepository.get_save_game(obj.id)
check("槽位/版本已清", g2.server_slot is None and g2.last_synced_version is None)

check("删除条目", AppRepository.delete_save_game(obj.id))
check("删除后为空", len(AppRepository.get_all_save_games()) == 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
