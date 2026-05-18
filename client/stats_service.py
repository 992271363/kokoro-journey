from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
from collections import defaultdict
import os

from local_database import SessionLocal
from local_models import AppDailyUsage, WatchedApplication


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


def get_weekly_stats() -> List[PeriodStat]:
    """返回从使用开始至今的所有自然周统计。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(AppDailyUsage.date, AppDailyUsage.focus_seconds, AppDailyUsage.lifetime_seconds)
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    for date_obj, focus, lifetime in rows:
        key, label = _iso_week_key(date_obj)
        groups[key]["focus"] += focus
        groups[key]["lifetime"] += lifetime
        groups[key]["label"] = label

    stats = [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]
    stats.sort(key=lambda x: x.key, reverse=True)
    return stats


def get_monthly_stats() -> List[PeriodStat]:
    """返回从使用开始至今的所有自然月统计。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(AppDailyUsage.date, AppDailyUsage.focus_seconds, AppDailyUsage.lifetime_seconds)
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    for date_obj, focus, lifetime in rows:
        key, label = _month_key(date_obj)
        groups[key]["focus"] += focus
        groups[key]["lifetime"] += lifetime
        groups[key]["label"] = label

    stats = [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]
    stats.sort(key=lambda x: x.key, reverse=True)
    return stats


def get_recent_daily_stats() -> List[PeriodStat]:
    """返回当前自然月（1号到今天）每一天的统计。"""
    today = datetime.now().date()
    first_day = today.replace(day=1)

    db = SessionLocal()
    try:
        rows = (
            db.query(AppDailyUsage.date, AppDailyUsage.focus_seconds, AppDailyUsage.lifetime_seconds)
            .filter(AppDailyUsage.date >= first_day)
            .filter(AppDailyUsage.date <= today)
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    for date_obj, focus, lifetime in rows:
        key, label = _day_key(date_obj)
        groups[key]["focus"] += focus
        groups[key]["lifetime"] += lifetime
        groups[key]["label"] = label

    stats = [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]
    stats.sort(key=lambda x: x.key, reverse=True)
    return stats


def get_all_daily_stats() -> List[PeriodStat]:
    """返回所有历史有数据的日期，按天聚合。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(AppDailyUsage.date, AppDailyUsage.focus_seconds, AppDailyUsage.lifetime_seconds)
            .all()
        )
    finally:
        db.close()

    groups: Dict[str, Dict] = defaultdict(lambda: {"focus": 0, "lifetime": 0, "label": ""})
    for date_obj, focus, lifetime in rows:
        key, label = _day_key(date_obj)
        groups[key]["focus"] += focus
        groups[key]["lifetime"] += lifetime
        groups[key]["label"] = label

    stats = [
        PeriodStat(
            key=k,
            label=v["label"],
            total_focus_seconds=v["focus"],
            total_lifetime_seconds=v["lifetime"],
        )
        for k, v in groups.items()
    ]
    stats.sort(key=lambda x: x.key, reverse=True)
    return stats


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
