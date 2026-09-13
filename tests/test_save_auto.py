"""云存档自动化：状态判定 / 登录同步策略 / 关联进程匹配（离线，云端调用打桩）。"""
import _common  # noqa: F401

import os
import sys
import tempfile

import core.save_auto as sa
import core.save_sync as ss
from db.repository import AppRepository

_common.ensure_db()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


class E:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# 本地目录 + 指纹
d = tempfile.mkdtemp(prefix="kokoro_auto_")
with open(os.path.join(d, "a.sav"), "wb") as f:
    f.write(b"x")
fp = ss.tree_fingerprint(d)

entry = E(id=1, server_id=10, name="G", local_path=d,
          local_fingerprint=fp, last_synced_version=3)

# --- entry_status ---
check("状态 一致", sa.entry_status(entry, {"latestVersion": 3})[0] == ss.STATUS_IN_SYNC)
check("状态 本地改动", sa.entry_status(entry, {"latestVersion": 3})[0] == ss.STATUS_IN_SYNC)
os.utime(os.path.join(d, "a.sav"), ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
check("状态 本地改动(改 mtime)", sa.entry_status(entry, {"latestVersion": 3})[0] == ss.STATUS_LOCAL)
check("状态 云端更新", sa.entry_status(entry, {"latestVersion": 5})[0] == ss.STATUS_CONFLICT)

# 本地未改动 + 云端更新
entry2 = E(id=2, server_id=10, name="G", local_path=d,
           local_fingerprint=ss.tree_fingerprint(d), last_synced_version=3)
check("状态 云端更新(本地未改)", sa.entry_status(entry2, {"latestVersion": 5})[0] == ss.STATUS_CLOUD)
check("状态 冲突(本地+云端)", sa.entry_status(entry, {"latestVersion": 5})[0] == ss.STATUS_CONFLICT)

# --- sync_entry_on_login 策略 ---
calls = {"upload": 0, "download": 0}
sa.AppRepository.mark_save_game_synced = lambda *a, **k: True
ss.upload_game = lambda *a, **k: (calls.__setitem__("upload", calls["upload"] + 1) or (True, {"server_id": 10, "version": 4, "fingerprint": "fp"}))
ss.list_versions = lambda *a, **k: (True, [{"id": 7, "versionNumber": 5}])
ss.prepare_download = lambda *a, **k: (calls.__setitem__("download", calls["download"] + 1) or (True, "/tmp/x"))
ss.apply_download = lambda *a, **k: (True, "")

check("策略 未关联云端跳过", sa.sync_entry_on_login("t", E(server_id=None), None)[1] == "未关联云端，跳过")
r = sa.sync_entry_on_login("t", entry, {"latestVersion": 3})
check("策略 本地改动->上传", r[0] and calls["upload"] == 1 and "已上传" in r[1])
r = sa.sync_entry_on_login("t", entry2, {"latestVersion": 5})
check("策略 云端更新->下载", r[0] and calls["download"] == 1 and "已下载" in r[1])
r = sa.sync_entry_on_login("t", entry, {"latestVersion": 5})
check("策略 冲突->跳过", r[0] and "冲突" in r[1])

# --- 关联进程匹配 ---
from core.tracker import add_or_get_watched_app  # noqa: E402
from db.database import SessionLocal  # noqa: E402

db = SessionLocal()
try:
    exe_path = r"C:\games\demo\game.exe"
    add_or_get_watched_app(db, exe_path, "game.exe")
finally:
    db.close()

g = AppRepository.create_save_game("Demo", d, linked_app_path=exe_path)
matched = sa.match_save_games_for_exe("game.exe")
check("按 exe 名称匹配到条目", any(m.id == g.id for m in matched))
check("不匹配的名字返回空", sa.match_save_games_for_exe("other.exe") == [])
AppRepository.delete_save_game(g.id)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
