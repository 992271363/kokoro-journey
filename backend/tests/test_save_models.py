"""云存档服务端模型测试：建表 / 唯一约束 / 字段形态（SQLite，无需 MariaDB）。"""
import os
import sys
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import sqlalchemy  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_db_path = _common.tmpfile("kokoro_save_models_", ".db")
_test_engine = _real_create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
sqlalchemy.create_engine = lambda *a, **k: _test_engine

from app import database, models  # noqa: E402

models.Base.metadata.create_all(bind=database.engine)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


insp = inspect(database.engine)
tables = set(insp.get_table_names())
for t in ("server_save_games", "server_save_versions", "server_save_files", "server_cloud_sessions"):
    check(f"表存在: {t}", t in tables)

cols = {c["name"] for c in insp.get_columns("server_save_files")}
check("save_files 含 relative_path/size/sha256/mtime_ns",
      {"relative_path", "size", "sha256", "mtime_ns"} <= cols)
check("save_files 仅一个 sha256 字段", len([c for c in cols if "sha256" in c]) == 1)

# 唯一约束：同用户同名游戏
session = database.SessionLocal()
user = models.User(username="t", hashed_password="x")
session.add(user)
session.commit()

session.add(models.ServerSaveGame(user_id=user.id, name="GameA"))
session.commit()
dup_ok = False
try:
    session.add(models.ServerSaveGame(user_id=user.id, name="GameA"))
    session.commit()
    dup_ok = True
except Exception:
    session.rollback()
check("同用户同名游戏被唯一约束拒绝", not dup_ok)

# 版本/文件基本写入
game = session.query(models.ServerSaveGame).first()
ver = models.ServerSaveVersion(game_id=game.id, version_number=1, status="committed",
                               total_size=3, file_count=1)
session.add(ver)
session.commit()
session.add(models.ServerSaveFile(version_id=ver.id, relative_path="a.sav",
                                  size=3, sha256="a" * 64, mtime_ns=123))
session.commit()
check("版本与文件清单可写入",
      session.query(models.ServerSaveFile).count() == 1)

session.close()
try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
