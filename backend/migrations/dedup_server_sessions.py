"""服务端会话去重迁移脚本。

默认 dry-run（只统计、不写入）。确认后才用 --apply 执行。

用法（在 backend/api 所在机器、且已设置 DATABASE_* 环境变量时运行）：
    python backend/migrations/dedup_server_sessions.py            # dry-run 统计
    python backend/migrations/dedup_server_sessions.py --apply    # 执行清理 + 建唯一约束

可选：
    --normalize-micro   若 session_start_time 列有小数秒（DATETIME_PRECISION>0），
                        先把整表时间截断到秒，再做去重（仅在你确认安全后使用）。

安全策略：
- dry-run 输出：列精度、小数秒行数、重复组/待删行、待删 focus_activity、受影响 summary、
  以及“归一化可能新增的冲突数”。
- --apply 前先把三张表完整导出到 backend/migrations/backups/ 作为备份；
  数据改动在事务中提交后创建 UNIQUE 约束；若建约束失败，尝试从备份还原。
- 不修改任何客户端代码，不改数据库以外的结构。
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

TABLES = (
    "server_app_usage_summary",
    "server_process_sessions",
    "server_focus_activities",
)

DUPLICATE_GROUPS_SQL = """
SELECT COUNT(*) AS dup_groups, COALESCE(SUM(c - 1), 0) AS rows_to_delete
FROM (
    SELECT summary_id, session_start_time, COUNT(*) AS c
    FROM server_process_sessions
    GROUP BY summary_id, session_start_time
    HAVING c > 1
) t
"""

AFFECTED_SUMMARIES_SQL = """
SELECT COUNT(DISTINCT summary_id)
FROM (
    SELECT summary_id
    FROM server_process_sessions
    GROUP BY summary_id, session_start_time
    HAVING COUNT(*) > 1
) d
"""

DUP_ACTIVITY_SQL = """
SELECT COUNT(*)
FROM server_focus_activities fa
WHERE fa.session_id IN (
    SELECT p.id
    FROM server_process_sessions p
    WHERE p.id <> (
        SELECT MIN(r.id)
        FROM server_process_sessions r
        WHERE r.summary_id = p.summary_id
          AND r.session_start_time = p.session_start_time
    )
)
"""

TRUNC_GROUPS_SQL = """
SELECT COUNT(*) AS dup_groups, COALESCE(SUM(c - 1), 0) AS rows_to_delete
FROM (
    SELECT summary_id, CAST(DATE_FORMAT(session_start_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS DATETIME) AS sec,
           COUNT(*) AS c
    FROM server_process_sessions
    GROUP BY summary_id, sec
    HAVING c > 1
) t
"""


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def fetch_stats(session) -> dict:
    cols = session.execute(text(
        """
        SELECT COLUMN_NAME, DATA_TYPE, DATETIME_PRECISION
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'server_process_sessions'
          AND COLUMN_NAME IN ('session_start_time', 'session_end_time')
        """
    )).fetchall()

    micro_rows = session.execute(text(
        "SELECT COUNT(*) FROM server_process_sessions "
        "WHERE MICROSECOND(session_start_time) <> 0"
    )).scalar()

    dup = session.execute(text(DUPLICATE_GROUPS_SQL)).fetchone()
    affected = session.execute(text(AFFECTED_SUMMARIES_SQL)).scalar()
    activities = session.execute(text(DUP_ACTIVITY_SQL)).scalar()
    trunc = session.execute(text(TRUNC_GROUPS_SQL)).fetchone()

    return {
        "columns": [(c[0], c[1], c[2]) for c in cols],
        "micro_rows": micro_rows or 0,
        "dup_groups": dup[0] or 0,
        "rows_to_delete": dup[1] or 0,
        "activities_to_delete": activities or 0,
        "affected_summaries": affected or 0,
        "trunc_groups": trunc[0] or 0,
        "trunc_rows_to_delete": trunc[1] or 0,
    }


def dump_tables(session) -> dict:
    backup = {}
    for t in TABLES:
        rows = session.execute(text(f"SELECT * FROM {t}")).mappings().all()
        backup[t] = [dict(r) for r in rows]
    return backup


def restore_from_backup(session, backup: dict) -> None:
    """从内存备份还原三张表（best-effort）。"""
    session.execute(text("DELETE FROM server_focus_activities"))
    session.execute(text("DELETE FROM server_process_sessions"))
    session.execute(text("DELETE FROM server_app_usage_summary"))
    # 按依赖顺序回填：summary → session → activity
    for t in ("server_app_usage_summary", "server_process_sessions", "server_focus_activities"):
        rows = backup.get(t, [])
        for row in rows:
            cols = ", ".join(f"`{k}`" for k in row.keys())
            params = ", ".join(f":{k}" for k in row.keys())
            session.execute(text(f"INSERT INTO {t} ({cols}) VALUES ({params})"), row)


def recompute_summaries(session, summary_ids) -> None:
    for sid in summary_ids:
        agg = session.execute(text(
            """
            SELECT SUM(total_lifetime_seconds) AS lt,
                   SUM(total_focus_seconds) AS ft,
                   MIN(session_start_time) AS first_start,
                   MAX(session_start_time) AS last_start
            FROM server_process_sessions
            WHERE summary_id = :sid
            """
        ), {"sid": sid}).fetchone()
        if agg is None or agg.lt is None:
            continue
        last_end = session.execute(text(
            """
            SELECT session_end_time
            FROM server_process_sessions
            WHERE summary_id = :sid AND session_start_time = :ls
            LIMIT 1
            """
        ), {"sid": sid, "ls": agg.last_start}).scalar()
        session.execute(text(
            """
            UPDATE server_app_usage_summary
            SET total_lifetime_seconds = :lt,
                total_focus_time_seconds = :ft,
                first_seen_at = :first_start,
                last_seen_start_at = :last_start,
                last_seen_end_at = :last_end
            WHERE id = :sid
            """
        ), {
            "lt": int(agg.lt), "ft": int(agg.ft),
            "first_start": agg.first_start, "last_start": agg.last_start,
            "last_end": last_end, "sid": sid,
        })


def apply_migration(session, normalize_micro: bool) -> None:
    stats = fetch_stats(session)
    summary_ids = [r[0] for r in session.execute(text(
        """
        SELECT DISTINCT summary_id FROM server_process_sessions
        GROUP BY summary_id, session_start_time HAVING COUNT(*) > 1
        """
    )).fetchall()]

    backup = dump_tables(session)
    backup_dir = Path(__file__).resolve().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"dedup_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup_path.write_text(
        json.dumps(backup, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    print(f"[migrate] 已备份三张表 -> {backup_path}")

    try:
        if normalize_micro:
            print("[migrate] 归一化 session_start_time 到秒 ...")
            session.execute(text(
                "UPDATE server_process_sessions "
                "SET session_start_time = CAST(DATE_FORMAT(session_start_time, "
                "'%Y-%m-%d %H:%i:%s') AS DATETIME)"
            ))

        print("[migrate] 删除重复会话的 focus_activities ...")
        session.execute(text(
            """
            DELETE fa FROM server_focus_activities fa
            JOIN server_process_sessions p ON fa.session_id = p.id
            WHERE p.id <> (
                SELECT MIN(r.id) FROM server_process_sessions r
                WHERE r.summary_id = p.summary_id
                  AND r.session_start_time = p.session_start_time
            )
            """
        ))

        print("[migrate] 删除重复会话（每组保留 MIN(id)）...")
        session.execute(text(
            """
            DELETE FROM server_process_sessions
            WHERE id NOT IN (
                SELECT keep_id FROM (
                    SELECT MIN(id) AS keep_id
                    FROM server_process_sessions
                    GROUP BY summary_id, session_start_time
                ) k
            )
            """
        ))

        print(f"[migrate] 重算 {len(summary_ids)} 个受影响 summary ...")
        recompute_summaries(session, summary_ids)
        session.commit()
    except Exception:
        session.rollback()
        print("[migrate] 数据阶段失败，从备份还原 ...")
        restore_from_backup(session, backup)
        session.commit()
        raise

    print("[migrate] 创建 UNIQUE 约束 ...")
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE server_process_sessions "
                "ADD CONSTRAINT uix_server_session_summary_start "
                "UNIQUE (summary_id, session_start_time)"
            ))
    except Exception as e:
        print(f"[migrate] 建唯一约束失败：{e}")
        print("[migrate] 从备份还原数据 ...")
        restore_from_backup(session, backup)
        session.commit()
        raise

    print("[migrate] 完成：去重 + 唯一约束已建立。")


def main() -> int:
    ap = argparse.ArgumentParser(description="服务端会话去重迁移")
    ap.add_argument("--apply", action="store_true", help="执行清理（默认只 dry-run）")
    ap.add_argument("--normalize-micro", action="store_true",
                    help="先把 session_start_time 截断到秒（仅确认安全后使用）")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        stats = fetch_stats(session)
        print("=" * 60)
        print("[migrate] 列精度（server_process_sessions）：")
        for name, dtype, prec in stats["columns"]:
            print(f"    {name}: {dtype}, DATETIME_PRECISION={prec}")
        print(f"[migrate] 小数秒行数                  : {stats['micro_rows']}")
        print(f"[migrate] 重复组数（按现有值）        : {stats['dup_groups']}")
        print(f"[migrate] 待删 session 数             : {stats['rows_to_delete']}")
        print(f"[migrate] 待删 focus_activity 数      : {stats['activities_to_delete']}")
        print(f"[migrate] 受影响 summary 数           : {stats['affected_summaries']}")
        print(f"[migrate] 归一到秒后重复组数          : {stats['trunc_groups']}")
        print(f"[migrate] 归一到秒后待删 session 数   : {stats['trunc_rows_to_delete']}")
        print("=" * 60)

        if not args.apply:
            print("[migrate] DRY-RUN：未做任何写入。确认无误后加 --apply 执行。")
            return 0

        apply_migration(session, normalize_micro=args.normalize_micro)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
