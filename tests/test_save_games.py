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

items = AppRepository.get_all_save_games()
check("列表返回 1 条", len(items) == 1 and items[0].local_path == r"C:\saves\game1")

check("更新名称", AppRepository.update_save_game(obj.id, name="改名游戏"))
check("名称已更新", AppRepository.get_save_game(obj.id).name == "改名游戏")

check("写入 server_id", AppRepository.set_save_game_server_id(obj.id, 42))
check("写入同步状态", AppRepository.mark_save_game_synced(obj.id, 3, "fp123"))
g = AppRepository.get_save_game(obj.id)
check("同步状态已保存",
      g.server_id == 42 and g.last_synced_version == 3
      and g.local_fingerprint == "fp123" and g.last_synced_at is not None)

check("删除条目", AppRepository.delete_save_game(obj.id))
check("删除后为空", len(AppRepository.get_all_save_games()) == 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
