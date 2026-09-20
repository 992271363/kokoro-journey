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
for t in ("server_save_games", "server_save_versions", "server_save_files",
          "server_save_slot_metas", "server_cloud_sessions"):
    check(f"表存在: {t}", t in tables)

cols = {c["name"] for c in insp.get_columns("server_save_files")}
check("save_files 含 relative_path/size/sha256/mtime_ns",
      {"relative_path", "size", "sha256", "mtime_ns"} <= cols)
check("save_files 仅一个 sha256 字段", len([c for c in cols if "sha256" in c]) == 1)

vcols = {c["name"] for c in insp.get_columns("server_save_versions")}
check("save_versions 含 slot", "slot" in vcols)
_vuq = insp.get_unique_constraints("server_save_versions")
check("slot 不参与唯一约束",
      all("slot" not in (c.get("column_names") or []) for c in _vuq))
_vidx = insp.get_indexes("server_save_versions")
check("存在 (game_id, slot) 索引",
      any((i.get("column_names") or []) == ["game_id", "slot"] for i in _vidx))

gcols = {c["name"] for c in insp.get_columns("server_save_games")}
check("save_games 含 identifier", "identifier" in gcols)
_guq = insp.get_unique_constraints("server_save_games")
check("唯一约束为 (user_id, identifier)",
      any((c.get("column_names") or []) == ["user_id", "identifier"] for c in _guq))
check("旧 (user_id, name) 唯一约束已移除",
      all((c.get("column_names") or []) != ["user_id", "name"] for c in _guq))

# 唯一约束：同用户标识符唯一；显示名称可重复
session = database.SessionLocal()
user = models.User(username="t", hashed_password="x")
session.add(user)
session.commit()

session.add(models.ServerSaveGame(user_id=user.id, name="GameA", identifier="game-a"))
session.commit()

dup_ok = False
try:
    session.add(models.ServerSaveGame(user_id=user.id, name="Other", identifier="game-a"))
    session.commit()
    dup_ok = True
except Exception:
    session.rollback()
check("同用户同标识符被唯一约束拒绝", not dup_ok)

name_ok = False
try:
    session.add(models.ServerSaveGame(user_id=user.id, name="GameA", identifier="game-b"))
    session.commit()
    name_ok = True
except Exception:
    session.rollback()
check("同用户重名（标识符不同）允许", name_ok)

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

# 存档位备注：唯一约束 + 删游戏级联
_mu = insp.get_unique_constraints("server_save_slot_metas")
check("slot_meta 唯一约束 (game_id, slot)",
      any((c.get("column_names") or []) == ["game_id", "slot"] for c in _mu))

game2 = models.ServerSaveGame(user_id=user.id, name="G2", identifier="g2")
session.add(game2)
session.commit()
session.add(models.ServerSaveSlotMeta(game_id=game2.id, slot=3, label="第三章"))
session.commit()
check("备注写入", session.query(models.ServerSaveSlotMeta).count() == 1)
session.delete(game2)
session.commit()
check("删游戏级联清备注", session.query(models.ServerSaveSlotMeta).count() == 0)

session.close()
try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
