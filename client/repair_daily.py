"""一次性修复脚本：按原始区间重建 app_daily_usage。

背景：app_daily_usage 是派生汇总表，历史导入路径曾直接从 JSON 写入它，而会话
按 summary_id + session_start_time 去重，两边不对称，导致出现大量"孤儿行"
（有日统计、无任何会话），统计界面因此显示出不可能的时长。

用法（在 client 目录下运行）：
    python repair_daily.py                  # 预览差异
    python repair_daily.py --apply          # 备份后执行重建
    python repair_daily.py --apply --db 路径\local_client.db

默认不改动数据库；加 --apply 会先在同目录生成 .bak-YYYYmmdd-HHMMSS 备份。
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys

from db.database import engine, Base
from core.daily_rebuild import rebuild_app_daily_usage
from core.stats import clear_distinct_cache, get_daily_distinct_totals

DEFAULT_DB = r"C:\Users\114514\AppData\Local\desktopActivitySystem\data\local_client.db"


def _summary(conn: sqlite3.Connection) -> dict:
    def one(sql: str) -> float:
        return conn.execute(sql).fetchone()[0] or 0

    return {
        "daily_rows": one("SELECT COUNT(*) FROM app_daily_usage"),
        "daily_focus": one("SELECT COALESCE(SUM(focus_seconds),0) FROM app_daily_usage") / 3600.0,
        "daily_lifetime": one("SELECT COALESCE(SUM(lifetime_seconds),0) FROM app_daily_usage") / 3600.0,
        "src_focus": one(
            "SELECT COALESCE(SUM(fa.focus_duration_seconds),0) FROM focus_activities fa"
            " JOIN process_sessions ps ON ps.id = fa.session_id"
            " JOIN app_usage_summary s ON s.id = ps.summary_id") / 3600.0,
        "src_lifetime": one("SELECT COALESCE(SUM(total_lifetime_seconds),0) FROM process_sessions") / 3600.0,
        "orphan_rows": one(
            "SELECT COUNT(*) FROM app_daily_usage d LEFT JOIN"
            " (SELECT DISTINCT s.application_id FROM process_sessions ps"
            "  JOIN app_usage_summary s ON s.id = ps.summary_id) x"
            " ON x.application_id = d.application_id WHERE x.application_id IS NULL"),
    }


def _print(title: str, s: dict) -> None:
    print(f"--- {title} ---")
    print(f"  日统计行数            : {s['daily_rows']}")
    print(f"  日统计 焦点合计        : {s['daily_focus']:.1f} h")
    print(f"  日统计 运行合计(按应用): {s['daily_lifetime']:.1f} h")
    print(f"  原始焦点区间合计       : {s['src_focus']:.1f} h")
    print(f"  原始会话运行合计(按应用): {s['src_lifetime']:.1f} h")
    print(f"  孤儿行(无会话的日统计) : {s['orphan_rows']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="重建 app_daily_usage 汇总表")
    parser.add_argument("--apply", action="store_true", help="实际执行（默认仅预览）")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"数据库路径（默认 {DEFAULT_DB}）")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return 2

    if args.apply:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = os.path.join(os.path.dirname(db_path), f"local_client.db.bak-{ts}")
        shutil.copy2(db_path, bak)
        print(f"已备份到: {bak}")
        print()

    Base.metadata.create_all(bind=engine)

    conn = sqlite3.connect(str(engine.url.database))
    try:
        before = _summary(conn)
        _print("修复前", before)
        conn.close()

        print()
        if not args.apply:
            print("预览模式：未做任何修改。确认无误后加 --apply 执行。")
            print("提示：无会话明细的遗留日期（旧版本数据）不会被删除。")
            return 0

        result = rebuild_app_daily_usage()
        clear_distinct_cache()

        conn = sqlite3.connect(str(engine.url.database))
        after = _summary(conn)
        _print("修复后", after)
        conn.close()

        print()
        print(f"  删除旧行 {result['deleted']} 条，写入新行 {result['written']} 条")
        print(f"  保留无源的遗留行 {result['legacy_kept']} 条"
              f"（{result['legacy_lifetime_seconds'] / 3600:.1f} h 运行 /"
              f" {result['legacy_focus_seconds'] / 3600:.1f} h 焦点，无法去重）")
        print(f"  因 focus > lifetime 被裁剪: {result['focus_clamped']} 秒")

        totals = get_daily_distinct_totals(force=True)
        focus_h = sum(v[0] for v in totals.values()) / 3600.0
        life_h = sum(v[1] for v in totals.values()) / 3600.0
        over24 = [d for d, v in totals.items() if v[1] > 86400]
        print()
        print(f"  统计口径合计: 运行 {life_h:.1f} h / 焦点 {focus_h:.1f} h，共 {len(totals)} 天")
        print(f"  单日运行 > 24h 的日期数: {len(over24)}")
        print()
        print("修复完成。")
        return 0
    except Exception as exc:
        print(f"重建失败，已回滚: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
