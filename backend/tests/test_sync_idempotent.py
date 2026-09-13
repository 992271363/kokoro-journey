"""后端同步幂等测试（SQLite，无需 MariaDB）。

在导入 app.* 之前把 sqlalchemy.create_engine 打桩为 SQLite 引擎，
从而不触碰正式数据库初始化代码。验证：
  1. 同一 session 提交两次 -> 仅 1 条 server session，summary 只累计一次；
  2. 不同 session_start_time -> 正常新增 2 条；
  3. daily 重复提交 -> 保持现有 upsert 幂等。
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_db_path = _common.tmpfile("kokoro_backend_test_", ".db")
_test_engine = _real_create_engine(
    f"sqlite:///{_db_path}", connect_args={"check_same_thread": False}
)
sqlalchemy.create_engine = lambda *a, **k: _test_engine

from app import database, models, schemas, main  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


session = database.SessionLocal()
user = models.User(username="tester", hashed_password="x")
session.add(user)
session.commit()


def make_dto(start, end, lifetime=60, focus=30, title="win"):
    return schemas.SyncProcessSession(
        uid="uid-1",
        executable_name="app.exe",
        executable_path=r"c:\app.exe",
        process_name="app.exe",
        session_start_time=start,
        session_end_time=end,
        total_lifetime_seconds=lifetime,
        total_focus_seconds=focus,
        activities=[
            schemas.SyncFocusActivity(
                window_title=title,
                focus_start_time=start,
                focus_end_time=end,
                focus_duration_seconds=focus,
            )
        ],
    )


# 起始时间带微秒，验证“归一化后仍能去重”
t0 = datetime(2026, 9, 13, 10, 0, 0, 123456)
dto0 = make_dto(t0, t0 + timedelta(minutes=1))

# --- 测试 1：同一 session 重复提交 ---
main.sync_sessions_from_client([dto0], db=session, current_user=user)
main.sync_sessions_from_client([dto0], db=session, current_user=user)
check("重复提交只产生 1 条 session",
      session.query(models.ServerProcessSession).count() == 1)
summary = session.query(models.ServerAppUsageSummary).first()
check("summary 只累计一次 lifetime", summary.total_lifetime_seconds == 60)
check("summary 只累计一次 focus", summary.total_focus_time_seconds == 30)
check("activities 未重复", session.query(models.ServerFocusActivity).count() == 1)

# --- 测试 2：不同 start time 正常新增 ---
t1 = t0 + timedelta(minutes=5)
dto1 = make_dto(t1, t1 + timedelta(minutes=1), lifetime=120, focus=90)
main.sync_sessions_from_client([dto1], db=session, current_user=user)
check("不同 start 产生 2 条 session",
      session.query(models.ServerProcessSession).count() == 2)
summary = session.query(models.ServerAppUsageSummary).first()
check("summary 累计两次 lifetime", summary.total_lifetime_seconds == 180)
check("summary 累计两次 focus", summary.total_focus_time_seconds == 120)
check("first_seen_at 为最早会话",
      summary.first_seen_at is not None
      and summary.first_seen_at.replace(microsecond=0) == t0.replace(microsecond=0))
check("last_seen_start_at 为最晚会话",
      summary.last_seen_start_at is not None
      and summary.last_seen_start_at.replace(microsecond=0) == t1.replace(microsecond=0))

# --- 测试 3：daily 幂等 upsert ---
daily_dto = schemas.SyncAppDailyUsage(
    uid="uid-1",
    date=datetime(2026, 9, 13).date(),
    lifetime_seconds=100,
    focus_seconds=50,
)
main.sync_daily_from_client([daily_dto], db=session, current_user=user)
main.sync_daily_from_client([daily_dto], db=session, current_user=user)
check("daily 重复提交仍 1 行",
      session.query(models.ServerAppDailyUsage).count() == 1)
daily = session.query(models.ServerAppDailyUsage).first()
check("daily 值正确", daily.lifetime_seconds == 100 and daily.focus_seconds == 50)

session.close()
try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
