"""云存档：把「版本历史」迁移到固定 10 个「存档位」。

默认 dry-run（只统计、不写入）。确认后加 --apply。

用法（在 backend/api 所在机器、且已设置 DATABASE_* 环境变量时运行）：
    python backend/migrations/map_versions_to_slots.py            # dry-run
    python backend/migrations/map_versions_to_slots.py --apply    # 执行

规则：
- 每个游戏按 committed 版本的 created_at 新→旧，依次放入存档位 1..SLOT_COUNT(10)；
- 超出 10 个的旧版本（数据行/文件清单/磁盘目录）删除；
- 为 server_save_versions 补 slot 列并建立 (game_id, slot) 普通索引（幂等）。
  注意：此处**不建唯一约束** —— 两阶段写入允许「旧 committed + 新 pending」同槽共存，
  「每槽至多一条 committed」由 commit_version 的覆盖逻辑保证。

安全：--apply 前把 server_save_versions / server_save_files 导出到
backend/migrations/backups/ 作为备份。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

from sqlalchemy import text  # noqa: E402
from app.database import engine, SessionLocal  # noqa: E402
from app import save_storage  # noqa: E402

TABLES = ("server_save_versions", "server_save_files")


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


def fetch_plan(session) -> list[dict]:
    """返回每个游戏的槽位分配计划（不写库）。"""
    games = session.execute(text("SELECT id, user_id, name FROM server_save_games")).fetchall()
    plan = []
    for gid, uid, name in games:
        rows = session.execute(text(
            """
            SELECT id, version_number FROM server_save_versions
            WHERE game_id = :g AND status = 'committed'
            ORDER BY created_at DESC, id DESC
            """
        ), {"g": gid}).fetchall()
        keep = rows[:save_storage.SLOT_COUNT]
        drop = rows[save_storage.SLOT_COUNT:]
        plan.append({
            "game_id": gid, "user_id": uid, "name": name,
            "assign": [(slot + 1, r[0], r[1]) for slot, r in enumerate(keep)],
            "drop": [(r[0], r[1]) for r in drop],
        })
    return plan


def dump_tables(session) -> dict:
    backup = {}
    for t in TABLES:
        rows = session.execute(text(f"SELECT * FROM {t}")).mappings().all()
        backup[t] = [dict(r) for r in rows]
    return backup


def apply_migration(session) -> None:
    plan = fetch_plan(session)

    if not _column_exists(session, "server_save_versions", "slot"):
        print("[migrate] 添加列 server_save_versions.slot ...")
        session.execute(text("ALTER TABLE server_save_versions ADD COLUMN slot INT NULL"))
        session.commit()

    backup = dump_tables(session)
    backup_dir = Path(__file__).resolve().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"slots_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup_path.write_text(
        json.dumps(backup, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    print(f"[migrate] 已备份 -> {backup_path}")

    assigned = dropped = 0
    for p in plan:
        for slot, vid, _vn in p["assign"]:
            session.execute(text("UPDATE server_save_versions SET slot = :s WHERE id = :i"),
                            {"s": slot, "i": vid})
            assigned += 1
        for vid, vn in p["drop"]:
            session.execute(text("DELETE FROM server_save_files WHERE version_id = :i"),
                            {"i": vid})
            session.execute(text("DELETE FROM server_save_versions WHERE id = :i"), {"i": vid})
            save_storage.remove_tree(
                save_storage.version_dir(p["user_id"], p["game_id"], vn))
            dropped += 1
    session.commit()
    print(f"[migrate] 已分配 {assigned} 个版本到存档位，删除 {dropped} 个超量旧版本。")

    print("[migrate] 建立 (game_id, slot) 索引 ...")
    try:
        with engine.begin() as conn:
            n = conn.execute(text(
                """
                SELECT COUNT(*) FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'server_save_versions'
                  AND INDEX_NAME = 'ix_server_save_version_game_slot'
                """
            )).scalar()
            if not n:
                conn.execute(text(
                    "CREATE INDEX ix_server_save_version_game_slot "
                    "ON server_save_versions (game_id, slot)"
                ))
    except Exception as e:  # 已存在或驱动差异：忽略
        print(f"[migrate] 跳过索引（可能已存在）：{e}")

    print("[migrate] 完成。")


def main() -> int:
    ap = argparse.ArgumentParser(description="云存档版本历史 -> 固定存档位迁移")
    ap.add_argument("--apply", action="store_true", help="执行迁移（默认只 dry-run）")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        plan = fetch_plan(session)
        total_assign = sum(len(p["assign"]) for p in plan)
        total_drop = sum(len(p["drop"]) for p in plan)
        print("=" * 60)
        print(f"[migrate] 游戏数            : {len(plan)}")
        print(f"[migrate] 将分配到存档位版本: {total_assign}")
        print(f"[migrate] 将删除的超量版本  : {total_drop}")
        for p in plan:
            if p["drop"]:
                print(f"    - {p['name']}({p['game_id']}): 删除 {len(p['drop'])} 个旧版本")
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
