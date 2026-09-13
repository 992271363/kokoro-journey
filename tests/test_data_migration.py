"""数据存储位置迁移：剪切、覆盖备份(.BackN)、use_target、失败保留源文件。"""
import _common  # noqa: F401

import os
import sys
import tempfile

from util.config import Settings
from util import migration
from util.path import is_data_dir_configured

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


root = tempfile.mkdtemp(prefix="kokoro_mig_")
src = os.path.join(root, "src")
dst = os.path.join(root, "dst")
os.makedirs(src)
os.makedirs(dst)
dbp = os.path.join(dst, "local_client.db")


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def reset_pending(mode):
    Settings().set("pendingDataMigration", {"from": src, "to": dst, "mode": mode})


# --- 备份编号 ---
write(dbp, b"t")
check("next_backup_path -> Back1", migration.next_backup_path(dbp).endswith(".Back1"))
write(dbp + ".Back1", b"x")
check("Back1 占用 -> Back2", migration.next_backup_path(dbp).endswith(".Back2"))
os.remove(dbp)
os.remove(dbp + ".Back1")

# --- move（目标为空）：剪切三个文件，旧 bak 保留 ---
write(os.path.join(src, "local_client.db"), b"SRCDB")
write(os.path.join(src, "failed_sessions.json"), b"FS")
write(os.path.join(src, "failed_sessions_dead.json"), b"FD")
write(os.path.join(src, "local_client_20200101.bak"), b"KEEP")
reset_pending("move")
migration.apply_pending_migration()
check("move: 目标 db 内容正确", os.path.exists(dbp) and read(dbp) == b"SRCDB")
check("move: 目标 failed_sessions", read(os.path.join(dst, "failed_sessions.json")) == b"FS")
check("move: 目标 dead queue", read(os.path.join(dst, "failed_sessions_dead.json")) == b"FD")
check("move: 源 db 已剪切", not os.path.exists(os.path.join(src, "local_client.db")))
check("move: 源队列已剪切", not os.path.exists(os.path.join(src, "failed_sessions.json")))
check("move: 旧 bak 保留未迁移", os.path.exists(os.path.join(src, "local_client_20200101.bak")))
check("move: 标记已清除", Settings().get("pendingDataMigration") is None)

# --- overwrite（目标已有 db）：备份 .Back1 后覆盖 ---
write(dbp, b"OLDDST")
write(os.path.join(src, "local_client.db"), b"NEWSRC")
write(os.path.join(src, "failed_sessions.json"), b"FS2")
reset_pending("overwrite")
migration.apply_pending_migration()
check("overwrite: 目标库已更新", read(dbp) == b"NEWSRC")
check("overwrite: 目标原库备份为 Back1", read(dbp + ".Back1") == b"OLDDST")
check("overwrite: 源库已剪切", not os.path.exists(os.path.join(src, "local_client.db")))
check("overwrite: 标记已清除", Settings().get("pendingDataMigration") is None)

# --- use_target：不动文件 ---
write(dbp, b"TARGET2")
write(os.path.join(src, "local_client.db"), b"SRC2")
reset_pending("use_target")
migration.apply_pending_migration()
check("use_target: 目标库不变", read(dbp) == b"TARGET2")
check("use_target: 源库保留", os.path.exists(os.path.join(src, "local_client.db")))
check("use_target: 标记已清除", Settings().get("pendingDataMigration") is None)

# --- 失败必须保留源文件 ---
write(os.path.join(src, "local_client.db"), b"FAILDB")
write(os.path.join(src, "failed_sessions.json"), b"FAILQ")
write(dbp, b"DSTFAIL")
_orig_copy2 = migration.shutil.copy2


def flaky(s, d, *a, **k):
    if str(d).endswith("failed_sessions.json"):
        raise OSError("模拟写入失败")
    return _orig_copy2(s, d, *a, **k)


migration.shutil.copy2 = flaky
reset_pending("overwrite")
migration.apply_pending_migration()
migration.shutil.copy2 = _orig_copy2
check("failure: 源 db 保留", os.path.exists(os.path.join(src, "local_client.db")))
check("failure: 源队列保留", os.path.exists(os.path.join(src, "failed_sessions.json")))
check("failure: 待迁移标记保留", isinstance(Settings().get("pendingDataMigration"), dict))

# --- is_data_dir_configured：有 dataDirectory 即已配置（不要求 db 存在） ---
Settings().set("dataDirectory", dst)
check("已配置: 有 dataDirectory 即 True", is_data_dir_configured() is True)
Settings().set("dataDirectory", None)
check("未配置: 无 dataDirectory 为 False", is_data_dir_configured() is False)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
