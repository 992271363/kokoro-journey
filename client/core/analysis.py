"""使用行为分析（时间模式 + 画像 + 对比）。

在"统计"（总量/排行）之上，回答：
- 什么时候专注最多（24 小时分布 / 7×24 热力图）
- 什么时候打开/关闭软件较多（会话开始/结束计数）
- 用户画像（作息/专注/碎片/活跃/集中度 + 雷达）
- 对比（今天↔昨天、本周↔上周、近30天↔前30天）

要点：
- 专注按"真实区间的秒数"落到小时桶（子小时精度，不取整到小时）；
- 结果带 TTL 内存缓存；`clear_analysis_cache()` 由 stats.clear_distinct_cache() 联动清理。
"""
from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time as time_type, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func

from db.database import SessionLocal
from db.models import (
    AppDailyUsage, AppUsageSummary, FocusActivity, ProcessSession, WatchedApplication,
)

SCOPE_TODAY = "today"
SCOPE_WEEK = "week"
SCOPE_30D = "30d"
SCOPE_ALL = "all"

SCOPE_LABELS = {
    SCOPE_TODAY: "今天",
    SCOPE_WEEK: "本周",
    SCOPE_30D: "近30天",
    SCOPE_ALL: "全部",
}

CONTINUOUS_GAP_SECONDS = 300  # 相邻专注间隔 <5min 视为同一段连续专注

# ---------------- 缓存 ----------------

_CACHE: Dict[tuple, tuple] = {}
_TTL = 60.0


def _cached(key: tuple, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit is not None and now - hit[0] < _TTL:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def clear_analysis_cache() -> None:
    _CACHE.clear()


# ---------------- 时间窗口 ----------------

def _now() -> datetime:
    return datetime.now()


def _scope_range(scope: str, now: Optional[datetime] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """返回 [start, end] 窗口；ALL 返回 (None, None) 表示不限。"""
    now = now or _now()
    today0 = datetime.combine(now.date(), time_type(0, 0, 0))
    if scope == SCOPE_TODAY:
        return today0, now
    if scope == SCOPE_WEEK:
        return today0 - timedelta(days=now.weekday()), now
    if scope == SCOPE_30D:
        return today0 - timedelta(days=29), now
    return None, None


def _scope_date_range(scope: str, now: Optional[datetime] = None):
    now = now or _now()
    today = now.date()
    if scope == SCOPE_TODAY:
        return today, today
    if scope == SCOPE_WEEK:
        return today - timedelta(days=now.weekday()), today
    if scope == SCOPE_30D:
        return today - timedelta(days=29), today
    return None, None


def _scope_days(scope: str, now: Optional[datetime], active_days: int) -> int:
    if scope == SCOPE_TODAY:
        return 1
    if scope == SCOPE_WEEK:
        return (now or _now()).weekday() + 1
    if scope == SCOPE_30D:
        return 30
    return max(active_days, 1)


def _iter_hour_segments(start: datetime, end: datetime,
                        scope_start: Optional[datetime],
                        scope_end: Optional[datetime]):
    """把 [start, end) 与 scope 求交后，按自然小时切分，产出每段的真实区间。"""
    if scope_start is not None and start < scope_start:
        start = scope_start
    if scope_end is not None and end > scope_end:
        end = scope_end
    if end <= start:
        return
    cur = start
    while cur < end:
        hour_start = cur.replace(minute=0, second=0, microsecond=0)
        nxt = hour_start + timedelta(hours=1)
        if nxt > end:
            nxt = end
        yield cur, nxt
        cur = nxt


def _union_seconds(intervals: List[Tuple[datetime, datetime]]) -> int:
    if not intervals:
        return 0
    intervals = sorted(intervals)
    total = 0.0
    cs, ce = intervals[0]
    for s, e in intervals[1:]:
        if s > ce:
            total += (ce - cs).total_seconds()
            cs, ce = s, e
        elif e > ce:
            ce = e
    total += (ce - cs).total_seconds()
    return int(total)


def _focus_intervals(scope_start, scope_end) -> List[Tuple[datetime, datetime]]:
    db = SessionLocal()
    try:
        q = db.query(FocusActivity.focus_start_time, FocusActivity.focus_end_time)
        if scope_start is not None:
            q = q.filter(FocusActivity.focus_end_time >= scope_start)
        if scope_end is not None:
            q = q.filter(FocusActivity.focus_start_time <= scope_end)
        rows = q.all()
    finally:
        db.close()

    out = []
    for start, end in rows:
        if start is None or end is None or end <= start:
            continue
        s = max(start, scope_start) if scope_start is not None else start
        e = min(end, scope_end) if scope_end is not None else end
        if e > s:
            out.append((s, e))
    return out


# ---------------- 24 小时分布 ----------------

def get_hourly_focus(scope: str) -> List[int]:
    """专注秒按小时（0–23）分布；跨小时/跨天按真实重叠秒累加。"""
    return _cached(("hourly_focus", scope), lambda: _compute_hourly_focus(scope))


def _compute_hourly_focus(scope: str) -> List[int]:
    ss, se = _scope_range(scope)
    buckets = [0.0] * 24
    for start, end in _focus_intervals(ss, se):
        for a, b in _iter_hour_segments(start, end, ss, se):
            buckets[a.hour] += (b - a).total_seconds()
    return [int(round(x)) for x in buckets]


def _compute_hourly_events(scope: str, column) -> List[int]:
    ss, se = _scope_range(scope)
    db = SessionLocal()
    try:
        q = db.query(column)
        if ss is not None:
            q = q.filter(column >= ss)
        if se is not None:
            q = q.filter(column <= se)
        rows = q.all()
    finally:
        db.close()
    buckets = [0] * 24
    for (t,) in rows:
        if t is not None:
            buckets[t.hour] += 1
    return buckets


def get_hourly_opens(scope: str) -> List[int]:
    """按小时统计"打开"次数（会话开始时间）。"""
    return _cached(("hourly_opens", scope),
                   lambda: _compute_hourly_events(scope, ProcessSession.session_start_time))


def get_hourly_closes(scope: str) -> List[int]:
    """按小时统计"关闭"次数（会话结束时间）。"""
    return _cached(("hourly_closes", scope),
                   lambda: _compute_hourly_events(scope, ProcessSession.session_end_time))


def get_weekday_hour_matrix(scope: str) -> List[List[int]]:
    """7×24 专注热力图：行=周一..周日，列=0..23 点。"""
    return _cached(("weekday_hour", scope), lambda: _compute_weekday_hour(scope))


def _compute_weekday_hour(scope: str) -> List[List[int]]:
    ss, se = _scope_range(scope)
    matrix = [[0.0] * 24 for _ in range(7)]
    for start, end in _focus_intervals(ss, se):
        for a, b in _iter_hour_segments(start, end, ss, se):
            matrix[a.weekday()][a.hour] += (b - a).total_seconds()
    return [[int(round(v)) for v in row] for row in matrix]


# ---------------- 窗口汇总 ----------------

def _window_totals(scope_start, scope_end) -> dict:
    db = SessionLocal()
    try:
        lq = db.query(ProcessSession.session_start_time, ProcessSession.session_end_time,
                      ProcessSession.total_lifetime_seconds)
        if scope_start is not None:
            lq = lq.filter(ProcessSession.session_end_time >= scope_start)
        if scope_end is not None:
            lq = lq.filter(ProcessSession.session_start_time <= scope_end)
        sessions = lq.all()
    finally:
        db.close()

    lifetime_intervals = []
    opens = closes = 0
    active_dates = set()
    for start, end, secs in sessions:
        if start is None:
            continue
        if end is None:
            end = start + timedelta(seconds=secs or 0)
        in_start = (scope_start is None or start >= scope_start) and \
                   (scope_end is None or start <= scope_end)
        if in_start:
            opens += 1
            active_dates.add(start.date())
        if (scope_start is None or end >= scope_start) and \
           (scope_end is None or end <= scope_end):
            closes += 1
        a = max(start, scope_start) if scope_start is not None else start
        b = min(end, scope_end) if scope_end is not None else end
        if b > a:
            lifetime_intervals.append((a, b))

    focus_intervals = _focus_intervals(scope_start, scope_end)
    return {
        "focus": _union_seconds(focus_intervals),
        "lifetime": _union_seconds(lifetime_intervals),
        "opens": opens,
        "closes": closes,
        "active_days": len(active_dates),
    }


def _continuous_focus_stats(scope_start, scope_end) -> Tuple[float, int]:
    """合并相邻 <5min 的专注区间，返回 (平均连续专注秒, 连续段数)。"""
    intervals = sorted(_focus_intervals(scope_start, scope_end))
    merged: List[List[datetime]] = []
    for a, b in intervals:
        if merged and (a - merged[-1][1]).total_seconds() < CONTINUOUS_GAP_SECONDS:
            if b > merged[-1][1]:
                merged[-1][1] = b
        else:
            merged.append([a, b])
    if not merged:
        return 0.0, 0
    total = sum((b - a).total_seconds() for a, b in merged)
    return total / len(merged), len(merged)


def _app_focus_concentration(scope: str) -> Tuple[float, float]:
    """返回 (Top1 专注占比, Top3 专注占比)。"""
    d0, d1 = _scope_date_range(scope)
    db = SessionLocal()
    try:
        q = db.query(
            WatchedApplication.executable_name,
            func.sum(AppDailyUsage.focus_seconds),
        ).join(WatchedApplication, WatchedApplication.id == AppDailyUsage.application_id)
        if d0 is not None:
            q = q.filter(AppDailyUsage.date >= d0)
        if d1 is not None:
            q = q.filter(AppDailyUsage.date <= d1)
        rows = q.group_by(WatchedApplication.id).all()
    finally:
        db.close()

    values = sorted((int(v or 0) for _, v in rows), reverse=True)
    total = sum(values)
    if total <= 0:
        return 0.0, 0.0
    return values[0] / total, sum(values[:3]) / total


# ---------------- 应用时段画像 ----------------

@dataclass
class AppHourStat:
    app_name: str
    peak_hour: int
    hourly: List[int]
    focus_seconds: int
    active_days: int
    avg_session_seconds: int
    focus_ratio: float


def get_app_hour_peaks(scope: str) -> List[AppHourStat]:
    return _cached(("app_hour", scope), lambda: _compute_app_hour_peaks(scope))


def _compute_app_hour_peaks(scope: str) -> List[AppHourStat]:
    ss, se = _scope_range(scope)
    d0, d1 = _scope_date_range(scope)

    db = SessionLocal()
    try:
        # 1) 每应用每小时的专注秒
        hq = db.query(
            WatchedApplication.executable_name,
            FocusActivity.focus_start_time,
            FocusActivity.focus_end_time,
        ).join(ProcessSession, ProcessSession.id == FocusActivity.session_id) \
         .join(AppUsageSummary, AppUsageSummary.id == ProcessSession.summary_id) \
         .join(WatchedApplication, WatchedApplication.id == AppUsageSummary.application_id)
        if ss is not None:
            hq = hq.filter(FocusActivity.focus_end_time >= ss)
        if se is not None:
            hq = hq.filter(FocusActivity.focus_start_time <= se)
        hourly_rows = hq.all()

        # 2) 每应用日汇总：专注/运行/活跃天数
        dq = db.query(
            WatchedApplication.executable_name,
            func.count(func.distinct(AppDailyUsage.date)),
            func.sum(AppDailyUsage.focus_seconds),
            func.sum(AppDailyUsage.lifetime_seconds),
        ).join(WatchedApplication, WatchedApplication.id == AppDailyUsage.application_id)
        if d0 is not None:
            dq = dq.filter(AppDailyUsage.date >= d0)
        if d1 is not None:
            dq = dq.filter(AppDailyUsage.date <= d1)
        daily_rows = dq.group_by(WatchedApplication.id).all()

        # 3) 每应用会话数（算平均单次专注）
        sq = db.query(
            WatchedApplication.executable_name,
            func.count(ProcessSession.id),
            func.sum(ProcessSession.total_focus_seconds),
        ).join(AppUsageSummary, AppUsageSummary.id == ProcessSession.summary_id) \
         .join(WatchedApplication, WatchedApplication.id == AppUsageSummary.application_id)
        if ss is not None:
            sq = sq.filter(ProcessSession.session_start_time >= ss)
        if se is not None:
            sq = sq.filter(ProcessSession.session_start_time <= se)
        session_rows = sq.group_by(WatchedApplication.id).all()
    finally:
        db.close()

    hourly_map: Dict[str, List[float]] = defaultdict(lambda: [0.0] * 24)
    focus_dates: Dict[str, set] = defaultdict(set)
    for name, start, end in hourly_rows:
        if start is None or end is None:
            continue
        key = os.path.splitext(name)[0]
        focus_dates[key].add(start.date())
        for a, b in _iter_hour_segments(start, end, ss, se):
            hourly_map[key][a.hour] += (b - a).total_seconds()

    daily_map: Dict[str, dict] = {}
    for name, days, focus, lifetime in daily_rows:
        daily_map[os.path.splitext(name)[0]] = {
            "active_days": int(days or 0),
            "focus": int(focus or 0),
            "lifetime": int(lifetime or 0),
        }

    session_map: Dict[str, Tuple[int, int]] = {}
    for name, cnt, focus in session_rows:
        session_map[os.path.splitext(name)[0]] = (int(cnt or 0), int(focus or 0))

    result: List[AppHourStat] = []
    for key, hours in hourly_map.items():
        ints = [int(round(v)) for v in hours]
        hourly_total = sum(ints)
        d = daily_map.get(key)
        if d is None:
            focus_secs = hourly_total
            active_days = len(focus_dates.get(key, set()))
            lifetime = 0
        else:
            focus_secs = d["focus"] or hourly_total
            active_days = d["active_days"] or len(focus_dates.get(key, set()))
            lifetime = d["lifetime"]
        cnt, sfocus = session_map.get(key, (0, 0))
        peak = max(range(24), key=lambda h: ints[h]) if any(ints) else -1
        result.append(AppHourStat(
            app_name=key,
            peak_hour=peak,
            hourly=ints,
            focus_seconds=focus_secs,
            active_days=active_days,
            avg_session_seconds=(sfocus // cnt) if cnt > 0 else 0,
            focus_ratio=(focus_secs / lifetime) if lifetime > 0 else 0.0,
        ))

    result.sort(key=lambda s: s.focus_seconds, reverse=True)
    return result


# ---------------- 画像 ----------------

@dataclass
class Persona:
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    radar: Dict[str, float] = field(default_factory=dict)
    features: Dict[str, float] = field(default_factory=dict)


def get_persona(scope: str) -> Persona:
    return _cached(("persona", scope), lambda: _compute_persona(scope))


def _compute_persona(scope: str) -> Persona:
    now = _now()
    ss, se = _scope_range(scope, now)
    hourly = get_hourly_focus(scope)
    total_focus = sum(hourly)

    if total_focus > 0:
        centroid = sum(h * v for h, v in enumerate(hourly)) / total_focus
        probs = [v / total_focus for v in hourly if v > 0]
        entropy = -sum(p * math.log(p) for p in probs) / math.log(24)
        early = sum(hourly[5:12]) / total_focus
        late = (sum(hourly[21:24]) + sum(hourly[0:5])) / total_focus
    else:
        centroid = entropy = early = late = 0.0

    totals = _window_totals(ss, se)
    focus = totals["focus"]
    lifetime = totals["lifetime"]
    active = totals["active_days"]
    focus_ratio = focus / lifetime if lifetime > 0 else 0.0
    avg_daily = focus / active if active > 0 else 0.0
    avg_cont, cont_n = _continuous_focus_stats(ss, se)
    top1, top3 = _app_focus_concentration(scope)

    matrix = get_weekday_hour_matrix(scope)
    weekday_sum = sum(sum(matrix[d]) for d in range(5))
    weekend_sum = sum(sum(matrix[d]) for d in range(5, 7))
    weekday_per_day = weekday_sum / 5 if weekday_sum > 0 else 0
    weekend_per_day = weekend_sum / 2 if weekend_sum > 0 else 0
    we_ratio = (weekend_per_day / weekday_per_day) if weekday_per_day > 0 else 0.0

    labels: List[str] = []
    if total_focus > 0:
        if early >= 0.4 and centroid < 18:
            labels.append("早鸟型")
        elif late >= 0.4:
            labels.append("夜猫型")
        else:
            labels.append("常规作息")
    if lifetime > 0:
        if focus_ratio >= 0.7:
            labels.append("专注度高")
        elif focus_ratio <= 0.4:
            labels.append("易分心")
    if cont_n > 0:
        if avg_cont < 300:
            labels.append("碎片化切换")
        elif avg_cont >= 900:
            labels.append("深度专注")
    if active > 0:
        if avg_daily >= 4 * 3600:
            labels.append("重度使用")
        elif avg_daily >= 3600:
            labels.append("中度使用")
        else:
            labels.append("轻度使用")
    if top1 >= 0.5:
        labels.append("单一应用重度")
    elif top1 > 0:
        labels.append("多应用均衡")
    if weekday_per_day > 0 and weekend_per_day > 0:
        if we_ratio > 1.2:
            labels.append("周末型")
        elif we_ratio < 0.6:
            labels.append("工作日型")

    days = _scope_days(scope, now, active)
    radar = {
        "专注度": round(focus_ratio * 100, 1),
        "规律性": round((1 - entropy) * 100, 1) if total_focus > 0 else 0.0,
        "时长": round(min(100.0, (avg_daily / 3600) / 8 * 100), 1),
        "集中度": round(top3 * 100, 1),
        "活跃度": round(min(100.0, active / days * 100), 1) if days > 0 else 0.0,
    }

    peak_hour = max(range(24), key=lambda h: hourly[h]) if total_focus > 0 else -1
    if peak_hour >= 0:
        summary = (f"{SCOPE_LABELS.get(scope, scope)}：约 {peak_hour:02d} 点前后专注最多"
                   f"（累计 {total_focus // 3600}h{total_focus % 3600 // 60:02d}m），"
                   + "、".join(labels) + "。")
    else:
        summary = f"{SCOPE_LABELS.get(scope, scope)}：暂无足够数据形成画像。"

    features = {
        "centroid_hour": round(centroid, 2),
        "early_ratio": round(early, 3),
        "late_ratio": round(late, 3),
        "entropy": round(entropy, 3),
        "focus_ratio": round(focus_ratio, 3),
        "avg_daily_seconds": int(avg_daily),
        "avg_continuous_seconds": int(avg_cont),
        "continuous_count": cont_n,
        "top1_share": round(top1, 3),
        "top3_share": round(top3, 3),
        "weekend_weekday_ratio": round(we_ratio, 3),
    }
    return Persona(labels=labels, summary=summary, radar=radar, features=features)


# ---------------- 对比 ----------------

def get_comparison(scope: str) -> Optional[dict]:
    """今天↔昨天、本周↔上周（对齐已过时长）、近30天↔前30天；ALL 返回 None。"""
    return _cached(("comparison", scope), lambda: _compute_comparison(scope))


def _delta(cur: int, prev: int) -> Tuple[int, Optional[float]]:
    d = cur - prev
    pct = (d / prev * 100.0) if prev > 0 else None
    return d, pct


def _compute_comparison(scope: str) -> Optional[dict]:
    if scope == SCOPE_ALL:
        return None

    now = _now()
    today0 = datetime.combine(now.date(), time_type(0, 0, 0))
    aligned = True

    if scope == SCOPE_TODAY:
        cur_ss, cur_se = today0, now
        prev_ss = today0 - timedelta(days=1)
        prev_se = prev_ss + (now - today0)
    elif scope == SCOPE_WEEK:
        monday = today0 - timedelta(days=now.weekday())
        cur_ss, cur_se = monday, now
        prev_ss = monday - timedelta(days=7)
        prev_se = prev_ss + (now - monday)
    else:  # 30D：两个同长度（30 天）窗口，不需对齐
        aligned = False
        cur_ss, cur_se = today0 - timedelta(days=29), now
        prev_ss = today0 - timedelta(days=59)
        prev_se = today0 - timedelta(days=29)

    cur = _window_totals(cur_ss, cur_se)
    prev = _window_totals(prev_ss, prev_se)

    df, dfp = _delta(cur["focus"], prev["focus"])
    dl, dlp = _delta(cur["lifetime"], prev["lifetime"])

    return {
        "scope": scope,
        "aligned": aligned,
        "current": {**cur, "start": cur_ss, "end": cur_se},
        "previous": {**prev, "start": prev_ss, "end": prev_se},
        "delta": {
            "focus": df, "focus_pct": dfp,
            "lifetime": dl, "lifetime_pct": dlp,
            "opens": cur["opens"] - prev["opens"],
            "closes": cur["closes"] - prev["closes"],
        },
    }
