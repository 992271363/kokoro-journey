"""升级迁移验证：把真实用户数据复制为“旧数据”样本，验证新版能安全打开/迁移。

可长期复用：每次版本升级前运行，确认旧库不被破坏、列补齐、备份保留上限生效。
注意：本测试只操作**副本**，绝不动真实数据。
"""
import _common  # noqa: F401

import os
import shutil
import sqlite3
import sys
import tempfile

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


real_root = _common.REAL_LOCALAPPDATA
if not real_root:
    print("[SKIP] 无 LOCALAPPDATA，跳过迁移测试")
    sys.exit(0)

src = os.path.join(real_root, "Kokoro Journey")
src_db = os.path.join(src, "data", "local_client.db")
if not os.path.isdir(src) or not os.path.exists(src_db):
    print(f"[SKIP] 未找到真实数据样本: {src_db}")
    sys.exit(0)

# 复制真实用户目录作为“旧数据”样本
old_root = tempfile.mkdtemp(prefix="kokoro_migration_")
old_dir = os.path.join(old_root, "Kokoro Journey")
try:
    shutil.copytree(src, old_dir)
except Exception as e:
    print(f"[SKIP] 复制样本失败（程序可能正在运行并锁定数据库）: {e}")
    sys.exit(0)

# 指向样本：设置目录 + 数据目录（必须在导入应用层之前）
os.environ["LOCALAPPDATA"] = old_root
old_data_dir = os.path.join(old_dir, "data")
old_db = os.path.join(old_data_dir, "local_client.db")
sys.argv.append("--data-dir=" + old_data_dir)

KEYS = ("watched_applications", "process_sessions", "focus_activities",
        "app_daily_usage", "app_groups")


def table_counts(path):
    con = sqlite3.connect(path)
    out = {}
    for t in KEYS:
        try:
            out[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
        except Exception:
            out[t] = None
    con.close()
    return out


def has_col(con, table, col):
    return any(row[1] == col for row in con.execute(f"PRAGMA table_info({table})"))


before = table_counts(old_db)
check("旧库可读且含数据表", any(v is not None for v in before.values()))

# 导入应用层并触发迁移
from db.database import create_db_and_tables, db_path  # noqa: E402

check("数据库路径指向样本", os.path.normcase(db_path) == os.path.normcase(old_db))
create_db_and_tables()

after = table_counts(old_db)
check("迁移后各表行数保持不变", before == after)

con = sqlite3.connect(old_db)
check("watched_applications.is_watched 列存在", has_col(con, "watched_applications", "is_watched"))
check("app_groups.sort_order 列存在", has_col(con, "app_groups", "sort_order"))
check("app_groups.color 列存在", has_col(con, "app_groups", "color"))
con.close()

# 设置缺失键回退默认
from util.config import Settings  # noqa: E402

s = Settings()
check("缺失设置键取默认值", s.get("__not_exist_key__", "default") == "default")

# 备份保留上限 5
from db import io as db_io  # noqa: E402

for i in range(6):
    p = os.path.join(old_data_dir, f"local_client_fake{i}.bak")
    with open(p, "w", encoding="utf-8") as f:
        f.write("x")
    os.utime(p, (1000 + i, 1000 + i))
db_io._backup_db()
baks = [f for f in os.listdir(old_data_dir)
        if f.startswith("local_client_") and f.endswith(".bak")]
check("备份文件保留上限 5", len(baks) <= 5)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
