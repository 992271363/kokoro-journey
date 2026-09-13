"""P4-1 换机闭环逻辑测试（离线，云端调用打桩；apply 用真实实现）。"""
import _common  # noqa: F401

import os
import sys
import tempfile

import core.save_bind as sb
import core.save_sync as ss

_common.ensure_db()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


class E:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# --- classify_cloud_binding ---
cloud = {"id": 5, "name": "A", "latestVersion": 3}
check("关系 已绑定", sb.classify_cloud_binding([E(id=1, server_id=5, name="A")], cloud) == sb.BOUND_SAME)
check("关系 新增", sb.classify_cloud_binding([E(id=1, server_id=1, name="B")], cloud) == sb.NEW)
check("关系 同名未绑定", sb.classify_cloud_binding([E(id=1, server_id=None, name="A")], cloud) == sb.NAME_UNBOUND)
check("关系 同名绑其它", sb.classify_cloud_binding([E(id=1, server_id=9, name="A")], cloud) == sb.NAME_OTHER)

# --- cloud_game_state ---
check("状态 云端已删除", sb.cloud_game_state(E(server_id=5), {}) == sb.STATE_DELETED)
check("状态 暂无版本", sb.cloud_game_state(E(server_id=5), {5: {"latestVersion": None}}) == sb.STATE_NO_VERSION)
check("状态 正常", sb.cloud_game_state(E(server_id=5), {5: {"latestVersion": 3}}) == sb.STATE_OK)
check("状态 未绑定视作正常", sb.cloud_game_state(E(server_id=None), {}) == sb.STATE_OK)

# --- 打桩 ---
created = []
marked = []
bound_to = []
sb.AppRepository.create_bound_save_game = staticmethod(
    lambda *a, **k: (created.append(a), E(id=99))[1])
sb.AppRepository.mark_save_game_synced = staticmethod(
    lambda *a, **k: (marked.append(a), True)[1])
sb.AppRepository.bind_save_game_to_server = staticmethod(
    lambda *a, **k: (bound_to.append(a), True)[1])

ss.tree_fingerprint = lambda path: "FP"


def make_tmp(local_path):
    tmp = local_path + ".__download_tmp__"
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "a.sav"), "wb") as f:
        f.write(b"x")
    return tmp


def reset():
    created.clear()
    marked.clear()
    bound_to.clear()


# --- 下载 NEW 成功 ---
base = tempfile.mkdtemp(prefix="kokoro_bind_")
local = os.path.join(base, "game_new")
reset()
ss.list_versions = lambda *a, **k: (True, [{"id": 7, "versionNumber": 3}])
ss.prepare_download = lambda token, sid, vid, target, progress_cb=None: (True, make_tmp(target))
ss.discard_download = lambda tmp: None
r = sb.download_cloud_game_to("t", dict(cloud), local, [])
check("NEW 下载成功", r[0] and r[1]["version"] == 3 and r[1]["local_id"] == 99)
check("NEW 创建了本地条目", len(created) == 1 and created[0][0] == "A" and created[0][1] == local)
check("NEW 落盘成功", os.path.isfile(os.path.join(local, "a.sav")))

# --- 下载失败（prepare 失败）：不创建条目 ---
local2 = os.path.join(base, "game_fail")
reset()
ss.prepare_download = lambda *a, **k: (False, "下载失败")
r = sb.download_cloud_game_to("t", dict(cloud), local2, [])
check("失败返回 False", r[0] is False)
check("失败不创建条目", len(created) == 0)

# --- 目录占用 ---
reset()
occ = [E(id=2, server_id=1, name="X", local_path=local)]
r = sb.download_cloud_game_to("t", dict(cloud), local, occ)
check("目录被占用被拒", r[0] is False and "占用" in r[1])

# --- 云端无版本 ---
reset()
r = sb.download_cloud_game_to("t", {"id": 5, "name": "A", "latestVersion": None}, os.path.join(base, "g"), [])
check("无版本被拒", r[0] is False and "暂无版本" in r[1])

# --- BOUND_SAME：不新建，仅标记 ---
local3 = os.path.join(base, "game_bound")
reset()
ss.prepare_download = lambda token, sid, vid, target, progress_cb=None: (True, make_tmp(target))
bound_entry = E(id=1, server_id=5, name="A", local_path=local3)
r = sb.download_cloud_game_to("t", dict(cloud), local3, [bound_entry])
check("已绑定：仅标记不新建", r[0] and len(created) == 0 and len(marked) == 1 and marked[0][0] == 1)

# --- bind_entry_id：绑定已有条目 ---
local4 = os.path.join(base, "game_bindexisting")
reset()
ss.prepare_download = lambda token, sid, vid, target, progress_cb=None: (True, make_tmp(target))
unbound = E(id=3, server_id=None, name="A", local_path=local4)
r = sb.download_cloud_game_to("t", dict(cloud), local4, [unbound], bind_entry_id=3)
check("绑定已有条目", r[0] and len(bound_to) == 1 and bound_to[0][0] == 3 and len(created) == 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
