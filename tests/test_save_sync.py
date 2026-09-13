"""云存档客户端逻辑测试（离线，不联网）：清单/指纹/校验/安全路径/状态/落盘。"""
import _common  # noqa: F401

import os
import sys
import tempfile

import core.save_sync as ss

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


base = tempfile.mkdtemp(prefix="kokoro_save_sync_")

# --- build_manifest ---
d = os.path.join(base, "save")
os.makedirs(os.path.join(d, "sub"))
with open(os.path.join(d, "b.sav"), "wb") as f:
    f.write(b"hello")
with open(os.path.join(d, "sub", "a.sav"), "wb") as f:
    f.write(b"world!")
manifest = ss.build_manifest(d)
check("manifest 条数", len(manifest) == 2)
check("manifest 路径排序", [m["path"] for m in manifest] == ["b.sav", "sub/a.sav"])
check("manifest 大小", manifest[1]["size"] == 6)
check("manifest 含 sha256", all(len(m["sha256"]) == 64 for m in manifest))
check("manifest 含 mtime_ns", all(isinstance(m["mtime_ns"], int) for m in manifest))

# --- 指纹随 mtime 变化 ---
fp1 = ss.tree_fingerprint(d)
fp2 = ss.tree_fingerprint(d)
check("指纹稳定", fp1 == fp2)
os.utime(os.path.join(d, "b.sav"), ns=(999999, 999999))
check("指纹随 mtime 变化", ss.tree_fingerprint(d) != fp1)

# --- validate_client_manifest ---
check("清单合法", ss.validate_client_manifest(manifest)[0])
check("单文件超 90MB 被拒", not ss.validate_client_manifest(
    [{"path": "x.sav", "size": ss.MAX_FILE_BYTES + 1, "sha256": "a" * 64}])[0])
check("总大小超 512MB 被拒", not ss.validate_client_manifest(
    [{"path": f"{i}", "size": 100 * 1024 * 1024, "sha256": "a" * 64} for i in range(6)])[0])
check("空清单被拒", not ss.validate_client_manifest([])[0])

# --- safe_join_local ---
check("安全路径正常", ss.safe_join_local(d, "sub/a.sav").endswith("a.sav"))


def raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


check("拒绝 .. 穿越", raises(lambda: ss.safe_join_local(d, "../evil")))
check("拒绝绝对路径", raises(lambda: ss.safe_join_local(d, "/etc/passwd")))
check("拒绝盘符路径", raises(lambda: ss.safe_join_local(d, "C:/x")))

# --- sync_status ---
check("状态: 未同步", ss.sync_status(False, False, False) == ss.STATUS_NOT_SYNCED)
check("状态: 一致", ss.sync_status(False, False, True) == ss.STATUS_IN_SYNC)
check("状态: 本地改动", ss.sync_status(True, False, True) == ss.STATUS_LOCAL)
check("状态: 云端更新", ss.sync_status(False, True, True) == ss.STATUS_CLOUD)
check("状态: 冲突", ss.sync_status(True, True, True) == ss.STATUS_CONFLICT)

# --- apply_download（备份 + 覆盖） ---
target = os.path.join(base, "local_game")
os.makedirs(target)
with open(os.path.join(target, "old.txt"), "wb") as f:
    f.write(b"OLD")
tmp = os.path.join(base, "local_game.__download_tmp__")
os.makedirs(tmp)
with open(os.path.join(tmp, "new.txt"), "wb") as f:
    f.write(b"NEW")
_mtime = 1_700_000_000_000_000_000  # 真实时间戳（100ns 粒度）
os.utime(os.path.join(tmp, "new.txt"), ns=(_mtime, _mtime))

ok_apply, backup = ss.apply_download(tmp, target)
check("apply 成功", ok_apply)
check("应用后新文件存在", os.path.exists(os.path.join(target, "new.txt")))
check("临时目录已消失", not os.path.exists(tmp))
check("备份存在且保留旧文件", backup and os.path.exists(os.path.join(backup, "old.txt")))
check("mtime 已恢复",
      abs(os.stat(os.path.join(target, "new.txt")).st_mtime_ns - _mtime) <= 1000)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
