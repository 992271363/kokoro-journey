import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_type, datetime, time as time_type, timedelta
from typing import Dict, List, Tuple

from db.database import SessionLocal
from db.models import AppDailyUsage, FocusActivity, ProcessSession, WatchedApplication
from sqlalchemy import func


@dataclass
class PeriodStat:
    """一个时间段（周、月、日）的聚合统计。"""
    key: str                 # 原始键，如 "2026-W20" 或 "2026-05" 或 "2026-05-19"
    label: str               # 展示标签
    total_focus_seconds: int
    total_lifetime_seconds: int


@dataclass
class AppPeriodStat:
    """某个时间段内，单个应用的统计。"""
    app_name: str
    focus_seconds: int
    lifetime_seconds: int


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def _get_iso_week_range(year: int, week: int) -> Tuple[datetime, datetime]:
    """返回某 ISO 周的起止日期（周一 00:00 ~ 周日 23:59）。"""
    jan4 = datetime(year, 1, 4)
    start = jan4 - timedelta(days=jan4.weekday())
    start = start + timedelta(weeks=week - 1)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def _iso_week_key(date_obj) -> Tuple[str, str]:
    """根据 date 对象返回 (key, label)。标签格式 MM/DD-MM/DD。"""
    iso = date_obj.isocalendar()
    year, week, _ = iso
    key = f"{year}-W{week:02d}"
    start, end = _get_iso_week_range(year, week)
    label = f"{year}: {start.month:02d}/{start.day:02d}-{end.month:02d}/{end.day:02d}"
    return key, label


def _month_key(date_obj) -> Tuple[str, str]:
    """根据 date 对象返回 (key, label)。"""
    key = date_obj.strftime("%Y-%m")
    label = date_obj.strftime("%Y年%m月")
    return key, label


def _day_key(date_obj) -> Tuple[str, str]:
    """根据 date 对象返回 (key, label)。"""
    key = date_obj.strftime("%Y-%m-%d")
    label = date_obj.strftime("%Y/%m/%d")
    return key, label


# --- 按日去重汇总（区间并集） ---
# 焦点在同一时刻只属于一个应用，按应用相加是安全的；但"运行时长"会把同时开着的
# 多个应用各自相加，单日上限 24 小时被轻松突破。因此运行时长改为当天所有会话
# 区间的并集（剔除重叠），焦点也走并集以兜住个别重复记录。
_DISTINCT_CACHE_TTL = 60.0
_distinct_cache = {"ts": 0.0, "data": None}


def clear_distinct_cache() -> None:
    """数据变化（会话入库、导入、重建）后调用，使下一次统计重新计算。"""
    _distinct_cache["ts"] = 0.0
    _distinct_cache["data"] = None


def _clip_into_day_buckets(
    buckets: Dict[date_type, List[Tuple[datetime, datetime]]],
    start: datetime,
    end: datetime,
) -> None:
    """把区间按自然日裁剪后放进对应日期的桶里。"""
    if end <= start:
        return
    day = start.date()
    last_day = end.date()
    while day <= last_day:
        seg_start = max(start, datetime.combine(day, time_type(0, 0, 0)))
        seg_end = min(end, datetime.combine(day + timedelta(days=1), time_type(0, 0, 0)))
        if seg_end > seg_start:
            buckets[day].append((seg_start, seg_end))
        day += timedelta(days=1)


def _union_seconds(intervals: List[Tuple[datetime, datetime]]) -> int:
    """区间并集总秒数：排序后线性扫描，自动剔除重叠部分。"""
    if not intervals:
        return 0
    intervals = sorted(intervals)
    total = 0.0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start > cur_end:
            total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        elif end > cur_end:
            cur_end = end
    total += (cur_end - cur_start).total_seconds()
    return int(total)


def get_daily_distinct_totals(force: bool = False,
                              include_legacy: bool = True
                              ) -> Dict[date_type, Tuple[int, int]]:
    """按自然日返回 (去重焦点秒, 去重运行秒)。

    有会话/焦点区间的日期用区间并集；早期版本只留下按应用累加的日统计、
    没有区间明细，那些日期无法去重，只能沿用汇总表原值，
    include_legacy=False 可排除这类日期。

    带 60 秒内存缓存，避免反复打开统计界面重复扫描全部区间。
    """
    now = time.time()
    if not force and _distinct_cache["data"] is not None \
            and now - _distinct_cache["ts"] < _DISTINCT_CACHE_TTL:
        return _distinct_cache["data"]

    db = SessionLocal()
    try:
        lifetime_rows = db.query(
            ProcessSession.session_start_time,
            ProcessSession.session_end_time,
            ProcessSession.total_lifetime_seconds,
        ).all()
        focus_rows = db.query(
            FocusActivity.focus_start_time,
            FocusActivity.focus_end_time,
        ).all()
        if include_legacy:
            legacy_rows = (
                db.query(
                    AppDailyUsage.date,
                    func.sum(AppDailyUsage.focus_seconds),
                    func.sum(AppDailyUsage.lifetime_seconds),
                )
                .group_by(AppDailyUsage.date)
                .all()
            )
        else:
            legacy_rows = []
    finally:
        db.close()

    lifetime_by_day: Dict[date_type, List[Tuple[datetime, datetime]]] = defaultdict(list)
    for start, end, secs in lifetime_rows:
        if start is None:
            continue
        if end is None:
            end = start + timedelta(seconds=secs or 0)
        _clip_into_day_buckets(lifetime_by_day, start, end)

    focus_by_day: Dict[date_type, List[Tuple[datetime, datetime]]] = defaultdict(list)
    for start, end in focus_rows:
        if start is not None and end is not None:
            _clip_into_day_buckets(focus_by_day, start, end)

    result: Dict[date_type, Tuple[int, int]] = {}
    for day in set(lifetime_by_day) | set(focus_by_day):
        result[day] = (
            _union_seconds(focus_by_day.get(day, [])),
            _union_seconds(lifetime_by_day.get(day, [])),
        )

    for day, focus, lifetime in legacy_rows:
        if day not in result:
            result[day] = (int(focus or 0), int(lifetime or 0))

    _distinct_cache["data"] = result
    _distinct_cache["ts"] = now
    return result


def _period_stats_from_daily(
    daily: Dict[date_type, Tuple[int, int]],
    key_func,
) -> List[PeriodStat]:
    """把按日去重结果聚合到某个时间段（周/月/日）。自然日互不重叠，可直接相加。"""
    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    for day in sorted(daily):
        key, label = key_func(day)
        focus, lifetime = daily[day]
        groups[key]["focus"] += focus
        groups[key]["lifetime"] += lifetime
        groups[key]["label"] = label

    return [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]


def get_weekly_stats() -> List[PeriodStat]:
    """返回从使用开始至今的所有自然周统计（运行时长已去重叠）。"""
    return _period_stats_from_daily(get_daily_distinct_totals(), _iso_week_key)


def get_monthly_stats() -> List[PeriodStat]:
    """返回从使用开始至今的所有自然月统计（运行时长已去重叠）。"""
    return _period_stats_from_daily(get_daily_distinct_totals(), _month_key)


def get_recent_daily_stats() -> List[PeriodStat]:
    """返回最近 30 天（今天往前 30 天，含空白日）每一天的统计。

    窗口固定为 30 天，无数据的日期也会以 0 值出现，保证用户随时打开
    看到的都是满窗口。右侧详情面板按天查询，零数据日点进去显示空列表。
    """
    today = datetime.now().date()
    start_day = today - timedelta(days=29)
    daily = get_daily_distinct_totals()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    day = start_day
    while day <= today:
        key, label = _day_key(day)
        focus, lifetime = daily.get(day, (0, 0))
        groups[key]["focus"] = focus
        groups[key]["lifetime"] = lifetime
        groups[key]["label"] = label
        day += timedelta(days=1)

    return [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]


def get_all_daily_stats() -> List[PeriodStat]:
    """返回所有历史有数据的日期，按天聚合。"""
    return _period_stats_from_daily(get_daily_distinct_totals(), _day_key)


def get_weekly_detail(week_key: str) -> List[AppPeriodStat]:
    """返回某周各软件的详细统计。"""
    year, week = int(week_key[:4]), int(week_key[6:])
    start, end = _get_iso_week_range(year, week)

    db = SessionLocal()
    try:
        rows = (
            db.query(
                WatchedApplication.executable_name,
                AppDailyUsage.focus_seconds,
                AppDailyUsage.lifetime_seconds,
            )
            .join(WatchedApplication, AppDailyUsage.application_id == WatchedApplication.id)
            .filter(AppDailyUsage.date >= start.date())
            .filter(AppDailyUsage.date <= end.date())
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0})
    for name, focus, lifetime in rows:
        groups[name]["focus"] += focus
        groups[name]["lifetime"] += lifetime

    return [
        AppPeriodStat(
            app_name=os.path.splitext(name)[0],
            focus_seconds=v["focus"],
            lifetime_seconds=v["lifetime"],
        )
        for name, v in groups.items()
    ]


def get_monthly_detail(month_key: str) -> List[AppPeriodStat]:
    """返回某月各软件的详细统计。"""
    year, month = int(month_key[:4]), int(month_key[5:])
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    db = SessionLocal()
    try:
        rows = (
            db.query(
                WatchedApplication.executable_name,
                AppDailyUsage.focus_seconds,
                AppDailyUsage.lifetime_seconds,
            )
            .join(WatchedApplication, AppDailyUsage.application_id == WatchedApplication.id)
            .filter(AppDailyUsage.date >= start.date())
            .filter(AppDailyUsage.date <= end.date())
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0})
    for name, focus, lifetime in rows:
        groups[name]["focus"] += focus
        groups[name]["lifetime"] += lifetime

    return [
        AppPeriodStat(
            app_name=os.path.splitext(name)[0],
            focus_seconds=v["focus"],
            lifetime_seconds=v["lifetime"],
        )
        for name, v in groups.items()
    ]


def get_daily_detail(date_key: str) -> List[AppPeriodStat]:
    """返回某一天各软件的详细统计。date_key 格式 YYYY-MM-DD。"""
    date_obj = datetime.strptime(date_key, "%Y-%m-%d").date()

    db = SessionLocal()
    try:
        rows = (
            db.query(
                WatchedApplication.executable_name,
                AppDailyUsage.focus_seconds,
                AppDailyUsage.lifetime_seconds,
            )
            .join(WatchedApplication, AppDailyUsage.application_id == WatchedApplication.id)
            .filter(AppDailyUsage.date == date_obj)
            .all()
        )
    finally:
        db.close()

    return [
        AppPeriodStat(
            app_name=os.path.splitext(name)[0],
            focus_seconds=focus,
            lifetime_seconds=lifetime,
        )
        for name, focus, lifetime in rows
        if focus > 0 or lifetime > 0
    ]
