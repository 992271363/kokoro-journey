"""云存档：为「云端游戏」补用户自定义标识符（拆分 名称 / 标识符）。

默认 dry-run（只统计、不写入）。确认后加 --apply。

用法（在能访问 DATABASE_* 环境变量的机器上运行）：
    python backend/migrations/add_save_game_identifier.py            # dry-run
    python backend/migrations/add_save_game_identifier.py --apply    # 执行

规则：
- 给 server_save_games 增加 identifier 列；
- 由现有 name 派生初始标识符（非法字符替换为 '-'，空则 'game-<id>'），
  同一用户内冲突时追加 '-<id>' 去重；
- 建立 (user_id, identifier) 唯一索引，并删除旧的 (user_id, name) 唯一索引
  （显示名称此后允许重名，配对一律走标识符）。

安全：--apply 前把 server_save_games 导出到 backend/migrations/backups/ 作为备份。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

from sqlalchemy import text  # noqa: E402
from app.database import engine, SessionLocal  # noqa: E402

TABLE = "server_save_games"
OLD_INDEX = "uix_server_save_game_user_name"
NEW_INDEX = "uix_server_save_game_user_identifier"

_INVALID = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _column_exists(session, table: str, column: str) -> bool:
    n = session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
        """
    ), {"t": table, "c": column}).scalar()
    return bool(n)


def _index_exists(session, table: str, index: str) -> bool:
    n = session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :i
        """
    ), {"t": table, "i": index}).scalar()
    return bool(n)


def _sanitize(name: str, fallback: str) -> str:
    value = _INVALID.sub("-", (name or "").strip()).strip("-._")
    value = value[:64]
    return value or fallback


def fetch_plan(session) -> list[dict]:
    """返回每个游戏的标识符分配计划（不写库）。"""
    rows = session.execute(text(
        f"SELECT id, user_id, name FROM {TABLE} ORDER BY user_id, id"
    )).fetchall()
    used: dict[int, set[str]] = {}
    plan = []
    for gid, uid, name in rows:
        taken = used.setdefault(uid, set())
        candidate = _sanitize(name, f"game-{gid}")
        identifier = candidate
        if identifier in taken:
            identifier = f"{candidate}-{gid}"[:64]
        taken.add(identifier)
        plan.append({"id": gid, "user_id": uid, "name": name,
                     "candidate": candidate, "identifier": identifier})
    return plan


def dump_table(session) -> list[dict]:
    rows = session.execute(text(f"SELECT * FROM {TABLE}")).mappings().all()
    return [dict(r) for r in rows]


def apply_migration(session) -> None:
    plan = fetch_plan(session)

    backup_dir = Path(__file__).resolve().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"save_game_identifier_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup_path.write_text(
        json.dumps({TABLE: dump_table(session)}, ensure_ascii=False,
                   default=_json_default),
        encoding="utf-8",
    )
    print(f"[migrate] 已备份 -> {backup_path}")

    if not _column_exists(session, TABLE, "identifier"):
        print("[migrate] 添加列 server_save_games.identifier ...")
        session.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN identifier VARCHAR(64) NULL"))
        session.commit()

    for p in plan:
        session.execute(text(
            f"UPDATE {TABLE} SET identifier = :i WHERE id = :id"
        ), {"i": p["identifier"], "id": p["id"]})
    session.commit()
    print(f"[migrate] 已为 {len(plan)} 个云端游戏写入标识符。")

    print("[migrate] 收紧为 NOT NULL ...")
    session.execute(text(f"ALTER TABLE {TABLE} MODIFY identifier VARCHAR(64) NOT NULL"))
    session.commit()

    print(f"[migrate] 建立唯一索引 {NEW_INDEX} ...")
    if not _index_exists(session, TABLE, NEW_INDEX):
        session.execute(text(
            f"CREATE UNIQUE INDEX {NEW_INDEX} ON {TABLE} (user_id, identifier)"
        ))
        session.commit()

    if _index_exists(session, TABLE, OLD_INDEX):
        print(f"[migrate] 删除旧的名称唯一索引 {OLD_INDEX} ...")
        try:
            session.execute(text(f"DROP INDEX {OLD_INDEX} ON {TABLE}"))
            session.commit()
        except Exception as e:  # 约束/索引名差异：忽略
            session.rollback()
            print(f"[migrate] 跳过删除旧索引：{e}")

    print("[migrate] 完成。")


def main() -> int:
    ap = argparse.ArgumentParser(description="云存档游戏：补用户自定义标识符")
    ap.add_argument("--apply", action="store_true", help="执行迁移（默认只 dry-run）")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        plan = fetch_plan(session)
        collisions = [p for p in plan if p["identifier"] != p["candidate"]]
        print("=" * 60)
        print(f"[migrate] 云端游戏数        : {len(plan)}")
        print(f"[migrate] 需去重的标识符    : {len(collisions)}")
        for p in plan[:20]:
            print(f"    - {p['id']:>4}  名称={p['name']!r} -> 标识符={p['identifier']!r}")
        if len(plan) > 20:
            print(f"    ...（其余 {len(plan) - 20} 条略）")
        print("=" * 60)
        if not args.apply:
            print("[migrate] DRY-RUN：未做任何写入。确认无误后加 --apply 执行。")
            return 0
        apply_migration(session)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
