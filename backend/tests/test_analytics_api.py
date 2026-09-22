"""活动分析接口测试（SQLite + TestClient）：时间模型 / 聚合口径 / 环比 / 并集 / 上限。"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_db_path = _common.tmpfile("kokoro_analytics_", ".db")
_test_engine = _real_create_engine(f"sqlite:///{_db_path}",
                                   connect_args={"check_same_thread": False})
sqlalchemy.create_engine = lambda *a, **k: _test_engine

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, database, models, main  # noqa: E402

client = TestClient(main.app)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# ── 造数据 ────────────────────────────────────────────────────
TZ = 480  # UTC+8

session = database.SessionLocal()
user = models.User(username="ana", hashed_password="x")
session.add(user)
session.commit()

app_a = models.ServerWatchedApplication(user_id=user.id, uid="u-a",
                                        executable_name="chrome.exe",
                                        executable_path=r"C:\chrome.exe")
app_b = models.ServerWatchedApplication(user_id=user.id, uid="u-b",
                                        executable_name="code.exe",
                                        executable_path=r"C:\code.exe")
session.add_all([app_a, app_b])
session.commit()
app_a_id, app_b_id = app_a.id, app_b.id

sum_a = models.ServerAppUsageSummary(application_id=app_a.id,
                                     total_lifetime_seconds=10800,
                                     total_focus_time_seconds=5400,
                                     first_seen_at=datetime(2026, 9, 1, 0, 0),
                                     last_seen_end_at=datetime(2026, 9, 16, 2, 15))
sum_b = models.ServerAppUsageSummary(application_id=app_b.id,
                                     total_lifetime_seconds=1200,
                                     total_focus_time_seconds=600)
session.add_all([sum_a, sum_b])
session.commit()


def daily(app_id, d, focus, lifetime):
    session.add(models.ServerAppDailyUsage(application_id=app_id, date=d,
                                           focus_seconds=focus, lifetime_seconds=lifetime))


daily(app_a.id, date(2026, 9, 13), 3000, 6000)
daily(app_a.id, date(2026, 9, 15), 3600, 7200)
daily(app_a.id, date(2026, 9, 16), 1800, 3600)
daily(app_b.id, date(2026, 9, 15), 600, 1200)
session.commit()

# 会话（UTC）：tz=480 时 S1 本地 09:00-09:30，S2 本地 09:45-10:15
s1 = models.ServerProcessSession(summary_id=sum_a.id, process_name="chrome.exe",
                                 session_start_time=datetime(2026, 9, 15, 1, 0),
                                 session_end_time=datetime(2026, 9, 15, 1, 30),
                                 total_lifetime_seconds=1800, total_focus_seconds=1800)
s2 = models.ServerProcessSession(summary_id=sum_a.id, process_name="chrome.exe",
                                 session_start_time=datetime(2026, 9, 15, 1, 45),
                                 session_end_time=datetime(2026, 9, 15, 2, 15),
                                 total_lifetime_seconds=1800, total_focus_seconds=1200)
session.add_all([s1, s2])
session.commit()
s1_id, s2_id = s1.id, s2.id

# 活动：Act2 与 Act3 在本地 10:00-10:10 重叠 → 并集应只算 600s（不是 1200s）
session.add_all([
    models.ServerFocusActivity(session_id=s1.id, window_title="GitHub - Chrome",
                               focus_start_time=datetime(2026, 9, 15, 1, 0),
                               focus_end_time=datetime(2026, 9, 15, 1, 30),
                               focus_duration_seconds=1800),
    models.ServerFocusActivity(session_id=s2.id, window_title="Docs",
                               focus_start_time=datetime(2026, 9, 15, 1, 45),
                               focus_end_time=datetime(2026, 9, 15, 2, 10),
                               focus_duration_seconds=1500),
    models.ServerFocusActivity(session_id=s2.id, window_title="Docs",
                               focus_start_time=datetime(2026, 9, 15, 2, 0),
                               focus_end_time=datetime(2026, 9, 15, 2, 10),
                               focus_duration_seconds=600),
])
session.commit()
session.close()

token = auth.create_access_token({"sub": "ana"})
H = {"Authorization": f"Bearer {token}"}


def get(path, **params):
    return client.get(path, params=params, headers=H)


# ── /analytics/summary ───────────────────────────────────────
r = get("/analytics/summary", **{"from": "2026-09-15", "to": "2026-09-16"})
cur = r.json()["current"]
check("summary 200", r.status_code == 200)
check("summary 总量/占比",
      cur["focusSeconds"] == 6000 and cur["lifetimeSeconds"] == 12000
      and cur["activeApps"] == 2 and cur["activeDays"] == 2
      and cur["focusRatio"] == 0.5)
chg = r.json()["change"]
check("summary 环比（前一等长周期 09-13~09-14）",
      chg["focus"] == 100.0 and chg["lifetime"] == 100.0
      and chg["activeApps"] == 100.0 and chg["activeDays"] == 100.0)
check("summary 最常用应用", r.json()["mostUsedApp"]["executableName"] == "chrome.exe")
check("summary range.days", r.json()["range"]["days"] == 2)

r = get("/analytics/summary", **{"from": "2026-09-17", "to": "2026-09-18"})
check("空周期 current 为 0 且环比 -100%",
      r.json()["current"]["focusSeconds"] == 0
      and r.json()["change"]["focus"] == -100.0
      and r.json()["mostUsedApp"] is None)

# ── /analytics/timeseries ────────────────────────────────────
r = get("/analytics/timeseries", **{"from": "2026-09-15", "to": "2026-09-16"})
pts = r.json()["points"]
check("timeseries 两点且聚合正确",
      len(pts) == 2 and pts[0]["focusSeconds"] == 4200 and pts[0]["lifetimeSeconds"] == 8400
      and pts[1]["focusSeconds"] == 1800)

r = get("/analytics/timeseries", **{"from": "2026-09-14", "to": "2026-09-16"})
pts = r.json()["points"]
check("timeseries 缺失日期补 0",
      len(pts) == 3 and pts[0]["date"] == "2026-09-14" and pts[0]["focusSeconds"] == 0)

# ── /analytics/apps ──────────────────────────────────────────
r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16", "tz": TZ})
items = r.json()["items"]
check("apps 默认按 focus 降序", [i["executableName"] for i in items] == ["chrome.exe", "code.exe"])
check("apps 聚合字段",
      items[0]["focusSeconds"] == 5400 and items[0]["activeDays"] == 2
      and items[0]["sessionCount"] == 2 and items[0]["avgSessionFocusSeconds"] == 1500)
check("apps focusRatio", items[0]["focusRatio"] == 0.5)

r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16", "sort": "name",
                              "order": "asc"})
check("apps 按名称升序",
      [i["executableName"] for i in r.json()["items"]] == ["chrome.exe", "code.exe"])

r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16", "q": "code"})
check("apps 搜索", [i["executableName"] for i in r.json()["items"]] == ["code.exe"])

r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16",
                              "pageSize": 1, "page": 1})
check("apps 分页 page1", r.json()["total"] == 2 and len(r.json()["items"]) == 1)
r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16",
                              "pageSize": 1, "page": 2})
check("apps 分页 page2", [i["executableName"] for i in r.json()["items"]] == ["code.exe"])

r = get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16", "include": "peak",
                              "tz": TZ})
check("apps peakHour（本地 9 点最高）", r.json()["items"][0]["peakHour"] == 9)
check("apps sort 非法 400",
      get("/analytics/apps", **{"from": "2026-09-15", "to": "2026-09-16",
                                "sort": "bogus"}).status_code == 400)

# ── /analytics/sessions ──────────────────────────────────────
r = get("/analytics/sessions", **{"from": "2026-09-15", "to": "2026-09-15", "tz": TZ})
data = r.json()
check("sessions 区间过滤（本地日）", data["total"] == 2)
check("sessions 按开始倒序", data["items"][0]["id"] == s2_id)
check("sessions activityCount", {i["id"]: i["activityCount"] for i in data["items"]}
      == {s2_id: 2, s1_id: 1})
check("sessions 归属字段", data["items"][0]["executableName"] == "chrome.exe")

# 跨 UTC 日但本地日不同：S2 的 01:45 UTC 属于本地 09-15；用 09-16 查应为空
check("sessions 本地日边界",
      get("/analytics/sessions", **{"from": "2026-09-16", "to": "2026-09-16",
                                    "tz": TZ}).json()["total"] == 0)

r = get(f"/analytics/sessions/{s1_id}/activities")
acts = r.json()
check("session activities", len(acts) == 1 and acts[0]["windowTitle"] == "GitHub - Chrome")

# ── /analytics/activity/hourly ───────────────────────────────
r = get("/analytics/activity/hourly", **{"from": "2026-09-15", "to": "2026-09-15",
                                         "tz": TZ, "metric": "focus"})
hourly = r.json()
check("hourly focus 并集（重叠不重复计）",
      hourly[9] == 2700 and hourly[10] == 600 and sum(hourly) == 3300)

r = get("/analytics/activity/hourly", **{"from": "2026-09-15", "to": "2026-09-15",
                                         "tz": TZ, "metric": "opens"})
check("hourly opens = session 开始次数", r.json()[9] == 2)

r = get("/analytics/activity/hourly", **{"from": "2026-09-15", "to": "2026-09-15",
                                         "tz": TZ, "metric": "closes"})
closes = r.json()
check("hourly closes = session 结束次数", closes[9] == 1 and closes[10] == 1)

check("hourly metric 非法 400",
      get("/analytics/activity/hourly", **{"from": "2026-09-15", "to": "2026-09-15",
                                           "metric": "x"}).status_code == 400)
check("hourly 超过 92 天 400",
      get("/analytics/activity/hourly", **{"from": "2026-01-01", "to": "2026-06-01",
                                           "tz": TZ}).status_code == 400)

# ── /analytics/activity/heatmap ──────────────────────────────
r = get("/analytics/activity/heatmap", **{"from": "2026-09-15", "to": "2026-09-15", "tz": TZ})
grid = r.json()
check("heatmap 7×24", len(grid) == 7 and all(len(row) == 24 for row in grid))
# 2026-09-15 是周二 → weekday()==1
check("heatmap 周二维度与数值", grid[1][9] == 2700 and grid[1][10] == 600)

# ── /analytics/apps/{app_id} ─────────────────────────────────
r = get(f"/analytics/apps/{app_a_id}", **{"from": "2026-09-15", "to": "2026-09-16", "tz": TZ})
detail = r.json()
check("app detail 摘要",
      detail["summary"]["focusSeconds"] == 5400 and detail["summary"]["sessionCount"] == 2
      and detail["summary"]["activeDays"] == 2)
check("app detail 日趋势", len(detail["series"]) == 2)
check("app detail hourly", detail["hourly"][9] == 2700 and detail["hourly"][10] == 600)
check("app detail topWindows 降序",
      len(detail["topWindows"]) >= 1
      and detail["topWindows"][0]["windowTitle"] == "Docs")
check("app detail 404", get("/analytics/apps/9999", **{"from": "2026-09-15",
                                                      "to": "2026-09-16"}).status_code == 404)
check("app detail 超过 92 天 400",
      get(f"/analytics/apps/{app_a_id}", **{"from": "2026-01-01",
                                            "to": "2026-06-01"}).status_code == 400)

# ── 鉴权 ─────────────────────────────────────────────────────
check("未登录 401", client.get("/analytics/summary",
                              params={"from": "2026-09-15", "to": "2026-09-16"}).status_code == 401)

try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
