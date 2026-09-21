"""用户偏好：为 user_preferences 补背景显示参数列（幂等，默认 dry-run）。

仅在「已部署过含 user_preferences 的版本」时需要；
若该表尚不存在（首次部署），启动时的 create_all 会直接建出含新列的表，无需运行本脚本。

用法：
    python backend/migrations/add_preference_display.py            # dry-run
    python backend/migrations/add_preference_display.py --apply    # 执行
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

from sqlalchemy import text  # noqa: E402
from app.database import engine, SessionLocal  # noqa: E402

TABLE = "user_preferences"
COLUMNS = (
    ("bg_mode", "ALTER TABLE user_preferences ADD COLUMN bg_mode VARCHAR(16) NOT NULL DEFAULT 'auto'"),
    ("bg_dim", "ALTER TABLE user_preferences ADD COLUMN bg_dim INT NULL"),
    ("bg_blur", "ALTER TABLE user_preferences ADD COLUMN bg_blur INT NULL"),
    ("bg_fit", "ALTER TABLE user_preferences ADD COLUMN bg_fit VARCHAR(16) NOT NULL DEFAULT 'cover'"),
)


def _table_exists(session) -> bool:
    n = session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
        """
    ), {"t": TABLE}).scalar()
    return bool(n)


def _column_exists(session, column: str) -> bool:
    n = session.execute(text(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c
        """
    ), {"t": TABLE, "c": column}).scalar()
    return bool(n)


def main() -> int:
    ap = argparse.ArgumentParser(description="user_preferences 补背景显示参数列")
    ap.add_argument("--apply", action="store_true", help="执行迁移（默认只 dry-run）")
    args = ap.parse_args()

    session = SessionLocal()
    try:
        if not _table_exists(session):
            print(f"[migrate] 表 {TABLE} 不存在：无需迁移（首次部署由 create_all 建表）。")
            return 0
        missing = [name for name, _sql in COLUMNS if not _column_exists(session, name)]
        print(f"[migrate] 缺失列: {missing or '无'}")
        if not missing:
            print("[migrate] 无需处理。")
            return 0
        if not args.apply:
            print("[migrate] DRY-RUN：未做任何写入。确认无误后加 --apply 执行。")
            return 0
        with engine.begin() as conn:
            for name, sql in COLUMNS:
                if name in missing:
                    print(f"[migrate] {sql}")
                    conn.execute(text(sql))
        print("[migrate] 完成。")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
