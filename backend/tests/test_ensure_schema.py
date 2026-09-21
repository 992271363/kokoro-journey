"""启动补列 ensure_schema：老库缺列 → 幂等补齐（列/索引/回填），可重复执行。"""
import os
import sys
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import sqlalchemy  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

_real_create_engine = sqlalchemy.create_engine

# 让 app.main 的 create_all 落在一个独立的临时库上（不影响下面构造的“老库”）
_import_db = _common.tmpfile("kokoro_schema_boot_", ".db")
_import_engine = _real_create_engine(f"sqlite:///{_import_db}",
                                     connect_args={"check_same_thread": False})
sqlalchemy.create_engine = lambda *a, **k: _import_engine

from app import main  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# ---- 构造一个“老版本”的库：缺 slot / identifier / bg_* ----
_old_db = _common.tmpfile("kokoro_schema_old_", ".db")
_old_engine = _real_create_engine(f"sqlite:///{_old_db}",
                                  connect_args={"check_same_thread": False})
with _old_engine.begin() as conn:
    conn.execute(text(
        "CREATE TABLE user_preferences ("
        "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
        "background VARCHAR(64) NOT NULL DEFAULT 'default:BG1', updated_at DATETIME)"
    ))
    conn.execute(text(
        "CREATE TABLE server_save_games ("
        "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
        "name VARCHAR(255) NOT NULL, created_at DATETIME, updated_at DATETIME)"
    ))
    conn.execute(text(
        "CREATE TABLE server_save_versions ("
        "id INTEGER PRIMARY KEY, game_id INTEGER NOT NULL, version_number INTEGER NOT NULL, "
        "status VARCHAR(16) NOT NULL, total_size BIGINT NOT NULL DEFAULT 0, "
        "file_count INTEGER NOT NULL DEFAULT 0, created_at DATETIME)"
    ))
    conn.execute(text(
        "INSERT INTO user_preferences (id, user_id, background) VALUES (1, 1, 'default:BG1')"
    ))
    conn.execute(text(
        "INSERT INTO server_save_games (id, user_id, name) VALUES (1, 1, 'MyGame')"
    ))

_main_insp = inspect(_import_engine)
check("新库不依赖 ensure_schema（user_preferences 已有 bg_mode）",
      "bg_mode" in {c["name"] for c in _main_insp.get_columns("user_preferences")})

# ---- 执行补列 ----
main.ensure_schema(engine=_old_engine)

insp = inspect(_old_engine)
up_cols = {c["name"] for c in insp.get_columns("user_preferences")}
check("补齐 bg_mode/bg_dim/bg_blur/bg_fit",
      {"bg_mode", "bg_dim", "bg_blur", "bg_fit"} <= up_cols)
check("server_save_games 补 identifier",
      "identifier" in {c["name"] for c in insp.get_columns("server_save_games")})
check("server_save_versions 补 slot",
      "slot" in {c["name"] for c in insp.get_columns("server_save_versions")})

with _old_engine.begin() as conn:
    bg_mode = conn.execute(text("SELECT bg_mode FROM user_preferences WHERE id = 1")).scalar()
    ident = conn.execute(text("SELECT identifier FROM server_save_games WHERE id = 1")).scalar()
check("已有行 bg_mode 取默认 auto", bg_mode == "auto")
check("identifier 由名称回填", ident == "MyGame")

idx = {i.get("name") for i in insp.get_indexes("server_save_versions")}
game_idx = {i.get("name") for i in insp.get_indexes("server_save_games")}
game_uq = {u.get("name") for u in insp.get_unique_constraints("server_save_games")}
check("补 slot 索引", "ix_server_save_version_game_slot" in idx)
check("补 identifier 唯一约束",
      "uix_server_save_game_user_identifier" in game_idx or
      "uix_server_save_game_user_identifier" in game_uq)

# ---- 幂等：重复执行不报错、不重复加列 ----
before = len(insp.get_columns("user_preferences"))
main.ensure_schema(engine=_old_engine)
after = len(inspect(_old_engine).get_columns("user_preferences"))
check("重复执行幂等", before == after)

_old_engine.dispose()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
