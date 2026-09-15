"""使用行为分析（时间模式/画像/对比）——离线合成数据，不联网。"""
import _common  # noqa: F401

import sys
from datetime import datetime

from db.database import SessionLocal
from db.models import (
    AppUsageSummary, FocusActivity, ProcessSession, WatchedApplication,
)
from core import analysis as an

_common.ensure_db()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


FIXED = datetime(2026, 5, 20, 15, 0, 0)  # 周三
an._now = lambda: FIXED  # 固定“当前时间”，保证窗口可预测

# --- 合成：一个会话 09:00–11:00，专注 09:30–10:15 ---
db = SessionLocal()
app = WatchedApplication(uid="u1", executable_name="Game.exe",
                         executable_path=r"C:\games\game.exe", is_watched=True)
db.add(app)
db.flush()
summary = AppUsageSummary(
    application_id=app.id, first_seen_at=FIXED, last_seen_start_at=FIXED,
    last_seen_end_at=FIXED, total_lifetime_seconds=7200, total_focus_time_seconds=2700,
)
db.add(summary)
db.flush()
sess = ProcessSession(
    summary_id=summary.id, process_name="game",
    session_start_time=datetime(2026, 5, 20, 9, 0, 0),
    session_end_time=datetime(2026, 5, 20, 11, 0, 0),
    total_lifetime_seconds=7200, total_focus_seconds=2700,
)
db.add(sess)
db.flush()
db.add(FocusActivity(
    session_id=sess.id, window_title="t",
    focus_start_time=datetime(2026, 5, 20, 9, 30, 0),
    focus_end_time=datetime(2026, 5, 20, 10, 15, 0),
    focus_duration_seconds=2700,
))
db.commit()
db.close()

an.clear_analysis_cache()

# --- 24 小时分布：真实秒精度（不取整到小时）---
hourly = an.get_hourly_focus(an.SCOPE_TODAY)
check("小时桶 9 点 = 1800s", hourly[9] == 1800)
check("小时桶 10 点 = 900s", hourly[10] == 900)
check("其余小时为 0", sum(hourly) == 2700 and hourly[9] + hourly[10] == 2700)

# --- 打开/关闭计数 ---
opens = an.get_hourly_opens(an.SCOPE_TODAY)
closes = an.get_hourly_closes(an.SCOPE_TODAY)
check("打开计数落在 9 点", opens[9] == 1 and sum(opens) == 1)
check("关闭计数落在 11 点", closes[11] == 1 and sum(closes) == 1)

# --- 7×24 热力图 ---
matrix = an.get_weekday_hour_matrix(an.SCOPE_TODAY)
check("热力图 周三(2) 9 点", matrix[2][9] == 1800)
check("热力图总和 = 2700", sum(sum(r) for r in matrix) == 2700)

# --- 窗口汇总 ---
totals = an._window_totals(datetime(2026, 5, 20, 0, 0, 0), FIXED)
check("窗口 focus=2700", totals["focus"] == 2700)
check("窗口 lifetime=7200", totals["lifetime"] == 7200)
check("窗口 opens/closes/active_days", totals["opens"] == 1 and totals["closes"] == 1
      and totals["active_days"] == 1)

# --- 应用时段画像 ---
peaks = an.get_app_hour_peaks(an.SCOPE_TODAY)
check("应用画像命中 1 个", len(peaks) == 1)
if peaks:
    check("应用峰值小时 9", peaks[0].peak_hour == 9)
    check("应用专注秒 2700", peaks[0].focus_seconds == 2700)

# --- 画像 ---
persona = an.get_persona(an.SCOPE_TODAY)
check("画像有标签", len(persona.labels) >= 1)
check("画像雷达 5 维", set(persona.radar.keys()) == {"专注度", "规律性", "时长", "集中度", "活跃度"})
check("画像重心在上午", 8 <= persona.features["centroid_hour"] <= 11)
check("画像摘要非空", bool(persona.summary))

# --- 对比口径 ---
cmp_today = an.get_comparison(an.SCOPE_TODAY)
check("TODAY 对比: 对齐", cmp_today is not None and cmp_today["aligned"] is True)
check("TODAY 对比: 当前 focus=2700/上期=0",
      cmp_today["current"]["focus"] == 2700 and cmp_today["previous"]["focus"] == 0)
check("TODAY 对比: 上期窗口为昨天",
      cmp_today["previous"]["start"] == datetime(2026, 5, 19, 0, 0, 0))

cmp_week = an.get_comparison(an.SCOPE_WEEK)
check("WEEK 对比: 对齐且本周从周一开始",
      cmp_week["aligned"] is True
      and cmp_week["current"]["start"] == datetime(2026, 5, 18, 0, 0, 0)
      and cmp_week["previous"]["start"] == datetime(2026, 5, 11, 0, 0, 0))

cmp_30 = an.get_comparison(an.SCOPE_30D)
check("30D 对比: 不对齐、同长度窗口",
      cmp_30["aligned"] is False
      and (cmp_30["current"]["end"] - cmp_30["current"]["start"]).days == 29
      and (cmp_30["previous"]["end"] - cmp_30["previous"]["start"]).days == 30)

check("ALL 不对比", an.get_comparison(an.SCOPE_ALL) is None)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
