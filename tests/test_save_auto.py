"""云存档自动化：状态判定 / 登录同步策略 / 关联进程匹配（离线，云端调用打桩）。

存档位模型：状态与「条目绑定的存档位」比较，槽位 versionId 即内容版本 id。
"""
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
d = _common.tmpdir("kokoro_auto_")
with open(os.path.join(d, "a.sav"), "wb") as f:
    f.write(b"x")
fp = ss.tree_fingerprint(d)

entry = E(id=1, server_id=10, name="G", local_path=d,
          local_fingerprint=fp, last_synced_version=3, server_slot=1)

# --- entry_status（slot_info 用 versionId）---
check("状态 一致", sa.entry_status(entry, {"slot": 1, "versionId": 3})[0] == ss.STATUS_IN_SYNC)
os.utime(os.path.join(d, "a.sav"), ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
check("状态 本地改动(改 mtime)", sa.entry_status(entry, {"slot": 1, "versionId": 3})[0] == ss.STATUS_LOCAL)
check("状态 冲突(本地+云端)", sa.entry_status(entry, {"slot": 1, "versionId": 5})[0] == ss.STATUS_CONFLICT)

# 本地未改动 + 云端更新
entry2 = E(id=2, server_id=10, name="G", local_path=d,
           local_fingerprint=ss.tree_fingerprint(d), last_synced_version=3, server_slot=1)
check("状态 云端更新(本地未改)", sa.entry_status(entry2, {"slot": 1, "versionId": 5})[0] == ss.STATUS_CLOUD)
check("状态 空槽位(无版本)", sa.entry_status(entry2, {"slot": 2, "versionId": None})[0] == ss.STATUS_IN_SYNC)

# --- sync_entry_on_login 策略 ---
calls = {"upload": 0, "download": 0}
_up = {}
sa.AppRepository.mark_save_game_synced = lambda *a, **k: True


def _fake_upload(*a, **k):
    calls["upload"] += 1
    _up["args"] = a
    _up["kwargs"] = k
    return True, {"server_id": 10, "slot": 2, "version_id": 4,
                  "version": 4, "fingerprint": "fp"}


ss.upload_game = _fake_upload
ss.prepare_download = lambda *a, **k: (calls.__setitem__("download", calls["download"] + 1) or (True, "/tmp/x"))
ss.apply_download = lambda *a, **k: (True, "")

slots_same = [{"slot": 1, "versionId": 3}]
slots_newer = [{"slot": 1, "versionId": 5}]

check("策略 未关联云端跳过", sa.sync_entry_on_login("t", E(server_id=None))[1] == "未关联云端，跳过")

ss.list_slots = lambda *a, **k: (True, [dict(s) for s in slots_same])
r = sa.sync_entry_on_login("t", entry)
check("策略 本地改动->上传", r[0] and calls["upload"] == 1 and "已上传" in r[1])
check("登录上传携带标识符与 server_id",
      _up["args"][3] == (getattr(entry, "identifier", None) or entry.name)
      and _up["kwargs"].get("server_id") == 10)

ss.list_slots = lambda *a, **k: (True, [dict(s) for s in slots_newer])
r = sa.sync_entry_on_login("t", entry2)
check("策略 云端更新->下载", r[0] and calls["download"] == 1 and "已下载" in r[1])

r = sa.sync_entry_on_login("t", entry)
check("策略 冲突->跳过", r[0] and "冲突" in r[1])

# --- upload_entry：未关联时先复用同名远端游戏，再自动选空槽 ---
ss.claim_device = lambda *a, **k: (True, {})
ss._find_remote_game_id = lambda *a, **k: 10
ss.list_slots = lambda *a, **k: (True, [{"slot": 1, "versionId": 11, "createdAt": "2026-01-01"},
                                        {"slot": 2, "versionId": None}])
_picked = {}
ss.upload_game = lambda t, p, n, ident=None, sid=None, slot=None, **k: (
    _picked.update({"sid": sid, "slot": slot, "identifier": ident}) or
    (True, {"server_id": sid, "slot": slot, "version_id": 5, "version": 5, "fingerprint": "fp"}))
e_unbound = E(id=9, server_id=None, name="G", local_path=d,
              local_fingerprint=fp, last_synced_version=None, server_slot=None)
ok_u, _res_u = sa.upload_entry("t", e_unbound)
check("自动上传复用同名远端并选空槽",
      ok_u and _picked.get("sid") == 10 and _picked.get("slot") == 2)

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
