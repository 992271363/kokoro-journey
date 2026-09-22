"""活动分析查询层（/analytics/*）。

设计要点：
- 时间模型：daily 使用客户端业务日期（server_app_daily_usage.date）；timestamp 使用
  UTC instant（sessions / activities）。二者不混。
- tz 语义：tz 为「分钟偏移」，本地时间 = UTC + tz 分钟（如 tz=480 → UTC+8）。
  日期范围统一由 business_date_range_to_utc() 转成 [start, end) 的半开 UTC 区间，
  sessions / activities / hourly / heatmap 全部复用同一个边界逻辑。
- 统计口径：
  * focus_ratio = focus / lifetime，lifetime=0 → 0；
  * avg_session_focus = focus / session_count，session_count=0 → 0；
  * summary 直接返回 current / previous / change（前一周期为等长紧邻周期），前端只显示；
  * hourly: focus=活动区间并集（避免重叠重复计），opens=session 开始次数，
    closes=session 结束次数；
  * heatmap 固定为 7×24 专注秒（无 metric 切换）。
- 成本：daily 类接口支持全历史；hourly / heatmap / peak 上限 MAX_ACTIVITY_DAYS 天。
- 旧 /dashboard/* 保留、不扩展，见 routers/dashboard.py（Deprecated）。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from .. import auth, database, models

router = APIRouter(prefix="/analytics", tags=["Analytics"])

MAX_ACTIVITY_DAYS = 92          # hourly / heatmap / peak 的最大区间（天）
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
_SORT_COLUMNS = {"focus", "lifetime", "active_days", "name"}


# ── 时间模型工具 ──────────────────────────────────────────────

def business_date_range_to_utc(
    date_from: date, date_to: date, tz_min: int
) -> tuple[datetime, datetime]:
    """业务日期区间 → [start, end) 的 naive-UTC 区间。

    本地时间 = UTC + tz_min；例如 2026-09-22~2026-09-22, tz=480 →
    2026-09-21 16:00 UTC ≤ ts < 2026-09-22 16:00 UTC。
    """
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="to 不能早于 from")
    tz = timezone(timedelta(minutes=tz_min))
    start_local = datetime(date_from.year, date_from.month, date_from.day, tzinfo=tz)
    end_local = datetime(date_to.year, date_to.month, date_to.day, tzinfo=tz) + timedelta(days=1)
    start = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start, end


def _range_days(date_from: date, date_to: date) -> int:
    return (date_to - date_from).days + 1


def _require_activity_range(date_from: date, date_to: date) -> None:
    if _range_days(date_from, date_to) > MAX_ACTIVITY_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"该分析最多支持 {MAX_ACTIVITY_DAYS} 天区间（全部范围请用最近 90 天）",
        )


def _local(dt: datetime, tz_min: int) -> datetime:
    return (dt + timedelta(minutes=tz_min)) if dt is not None else None


def _pct(current: int, previous: int) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 2)


def _ratio(focus: int, lifetime: int) -> float:
    if not lifetime:
        return 0.0
    return round(focus / lifetime, 4)


def _merge_seconds(segments: list[tuple[datetime, datetime]]) -> float:
    """把区间列表做并集后求总秒数（重叠不重复计）。"""
    if not segments:
        return 0.0
    segments = sorted(s for s in segments if s[1] > s[0])
    total = 0.0
    cur_start, cur_end = segments[0]
    for start, end in segments[1:]:
        if start > cur_end:
            total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    total += (cur_end - cur_start).total_seconds()
    return total


def _user_app_ids(db: Session, user_id: int) -> list[int]:
    rows = db.query(models.ServerWatchedApplication.id).filter_by(user_id=user_id).all()
    return [r[0] for r in rows]


def _daily_scope(db: Session, user_id: int):
    """用户 + 应用 关联后的 daily 查询基（未加日期过滤）。"""
    return db.query(models.ServerAppDailyUsage).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppDailyUsage.application_id,
    ).filter(models.ServerWatchedApplication.user_id == user_id)


# ── /summary ─────────────────────────────────────────────────

def _metrics(db: Session, user_id: int, date_from: date, date_to: date) -> dict:
    row = _daily_scope(db, user_id).filter(
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
    ).with_entities(
        func.coalesce(func.sum(models.ServerAppDailyUsage.focus_seconds), 0),
        func.coalesce(func.sum(models.ServerAppDailyUsage.lifetime_seconds), 0),
        func.count(distinct(models.ServerAppDailyUsage.application_id)),
    ).one()
    focus, lifetime, active_apps = int(row[0]), int(row[1]), int(row[2])

    active_days = db.query(
        func.count(distinct(models.ServerAppDailyUsage.date))
    ).select_from(models.ServerAppDailyUsage).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppDailyUsage.application_id,
    ).filter(
        models.ServerWatchedApplication.user_id == user_id,
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
        (models.ServerAppDailyUsage.focus_seconds > 0)
        | (models.ServerAppDailyUsage.lifetime_seconds > 0),
    ).scalar() or 0

    return {
        "focusSeconds": focus,
        "lifetimeSeconds": lifetime,
        "activeApps": active_apps,
        "activeDays": int(active_days),
        "focusRatio": _ratio(focus, lifetime),
    }


@router.get("/summary")
def summary(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """当前范围总体摘要 + 前一个等长紧邻周期的环比。"""
    days = _range_days(date_from, date_to)
    current = _metrics(db, current_user.id, date_from, date_to)

    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=days - 1)
    previous = _metrics(db, current_user.id, prev_from, prev_to)
    change = {
        "focus": _pct(current["focusSeconds"], previous["focusSeconds"]),
        "lifetime": _pct(current["lifetimeSeconds"], previous["lifetimeSeconds"]),
        "activeApps": _pct(current["activeApps"], previous["activeApps"]),
        "activeDays": _pct(current["activeDays"], previous["activeDays"]),
    }

    top = _daily_scope(db, current_user.id).filter(
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
    ).with_entities(
        models.ServerAppDailyUsage.application_id,
        func.sum(models.ServerAppDailyUsage.focus_seconds).label("focus"),
    ).group_by(models.ServerAppDailyUsage.application_id).order_by(
        func.sum(models.ServerAppDailyUsage.focus_seconds).desc()
    ).first()

    most_used = None
    if top is not None and int(top[1] or 0) > 0:
        app = db.query(models.ServerWatchedApplication).filter_by(id=top[0]).first()
        most_used = {
            "appId": top[0],
            "executableName": app.executable_name if app else "",
            "focusSeconds": int(top[1] or 0),
        }

    return {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat(), "days": days},
        "current": current,
        "previous": previous,
        "change": change,
        "mostUsedApp": most_used,
    }


# ── /timeseries ──────────────────────────────────────────────

@router.get("/timeseries")
def timeseries(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    bucket: str = Query("day"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """按业务日期聚合的趋势（缺失日期补 0）。"""
    if bucket != "day":
        raise HTTPException(status_code=400, detail="暂仅支持 bucket=day")

    rows = _daily_scope(db, current_user.id).filter(
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
    ).with_entities(
        models.ServerAppDailyUsage.date,
        func.sum(models.ServerAppDailyUsage.focus_seconds),
        func.sum(models.ServerAppDailyUsage.lifetime_seconds),
    ).group_by(models.ServerAppDailyUsage.date).all()

    by_date = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in rows}
    points = []
    cursor = date_from
    while cursor <= date_to:
        focus, lifetime = by_date.get(cursor, (0, 0))
        points.append({
            "date": cursor.isoformat(),
            "focusSeconds": focus,
            "lifetimeSeconds": lifetime,
        })
        cursor += timedelta(days=1)
    return {"bucket": "day", "points": points}


# ── /apps ────────────────────────────────────────────────────

@router.get("/apps")
def apps(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    tz: int = Query(0, ge=-1440, le=1440),
    q: str = Query(""),
    sort: str = Query("focus"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    include: str = Query(""),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """应用聚合排行（服务端聚合 + 搜索/排序/分页）；include=peak 时附带高峰小时。"""
    if sort not in _SORT_COLUMNS:
        raise HTTPException(status_code=400, detail="sort 非法")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="order 非法")
    if include not in ("", "peak"):
        raise HTTPException(status_code=400, detail="include 非法")

    start_utc, end_utc = business_date_range_to_utc(date_from, date_to, tz)
    user_app_ids = _user_app_ids(db, current_user.id)
    if not user_app_ids:
        return {"total": 0, "page": page, "pageSize": page_size, "items": []}

    daily_rows = db.query(
        models.ServerAppDailyUsage.application_id,
        func.sum(models.ServerAppDailyUsage.focus_seconds),
        func.sum(models.ServerAppDailyUsage.lifetime_seconds),
        func.count(distinct(models.ServerAppDailyUsage.date)),
    ).filter(
        models.ServerAppDailyUsage.application_id.in_(user_app_ids),
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
    ).group_by(models.ServerAppDailyUsage.application_id).all()
    daily_map = {r[0]: (int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)) for r in daily_rows}

    sess_rows = db.query(
        models.ServerAppUsageSummary.application_id,
        func.count(models.ServerProcessSession.id),
        func.coalesce(func.sum(models.ServerProcessSession.total_focus_seconds), 0),
    ).join(
        models.ServerProcessSession,
        models.ServerProcessSession.summary_id == models.ServerAppUsageSummary.id,
    ).filter(
        models.ServerAppUsageSummary.application_id.in_(user_app_ids),
        models.ServerProcessSession.session_start_time >= start_utc,
        models.ServerProcessSession.session_start_time < end_utc,
    ).group_by(models.ServerAppUsageSummary.application_id).all()
    sess_map = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in sess_rows}

    apps_meta = db.query(models.ServerWatchedApplication).filter(
        models.ServerWatchedApplication.id.in_(user_app_ids)
    ).all()
    summary_map = {s.application_id: s for s in db.query(models.ServerAppUsageSummary).filter(
        models.ServerAppUsageSummary.application_id.in_(user_app_ids)).all()}

    ql = (q or "").strip().lower()
    items = []
    for app in apps_meta:
        focus, lifetime, active_days = daily_map.get(app.id, (0, 0, 0))
        if focus == 0 and lifetime == 0:
            continue
        if ql and ql not in (app.executable_name or "").lower():
            continue
        session_count, session_focus = sess_map.get(app.id, (0, 0))
        summary_row = summary_map.get(app.id)
        items.append({
            "appId": app.id,
            "executableName": app.executable_name,
            "focusSeconds": focus,
            "lifetimeSeconds": lifetime,
            "focusRatio": _ratio(focus, lifetime),
            "activeDays": active_days,
            "sessionCount": session_count,
            "avgSessionFocusSeconds": int(session_focus / session_count) if session_count else 0,
            "firstSeenAt": summary_row.first_seen_at if summary_row else None,
            "lastSeenAt": summary_row.last_seen_end_at if summary_row else None,
            "peakHour": None,
        })

    reverse = order == "desc"
    if sort == "name":
        items.sort(key=lambda x: (x["executableName"] or "").lower(), reverse=reverse)
    else:
        key = {"focus": "focusSeconds", "lifetime": "lifetimeSeconds", "active_days": "activeDays"}[sort]
        items.sort(key=lambda x: x[key], reverse=reverse)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    if include == "peak" and page_items:
        page_ids = [it["appId"] for it in page_items]
        peaks = _peak_hours(db, current_user.id, page_ids, start_utc, end_utc, tz)
        for it in page_items:
            it["peakHour"] = peaks.get(it["appId"])

    return {"total": total, "page": page, "pageSize": page_size, "items": page_items}


def _peak_hours(db: Session, user_id: int, app_ids: list[int],
                start_utc: datetime, end_utc: datetime, tz: int) -> dict:
    rows = db.query(
        models.ServerAppUsageSummary.application_id,
        models.ServerFocusActivity.focus_start_time,
        models.ServerFocusActivity.focus_end_time,
    ).join(
        models.ServerProcessSession,
        models.ServerProcessSession.summary_id == models.ServerAppUsageSummary.id,
    ).join(
        models.ServerFocusActivity,
        models.ServerFocusActivity.session_id == models.ServerProcessSession.id,
    ).filter(
        models.ServerAppUsageSummary.application_id.in_(app_ids),
        models.ServerFocusActivity.focus_start_time.isnot(None),
        models.ServerFocusActivity.focus_end_time.isnot(None),
        models.ServerFocusActivity.focus_start_time < end_utc,
        models.ServerFocusActivity.focus_end_time > start_utc,
    ).all()

    buckets: dict[int, list[list]] = defaultdict(lambda: [[] for _ in range(24)])
    for app_id, a, b in rows:
        for hour, seg_start, seg_end in _split_local_hours(a, b, tz, start_utc, end_utc):
            buckets[app_id][hour].append((seg_start, seg_end))

    peaks = {}
    for app_id, hours in buckets.items():
        best_hour, best_seconds = None, 0.0
        for hour in range(24):
            secs = _merge_seconds(hours[hour])
            if secs > best_seconds:
                best_hour, best_seconds = hour, secs
        peaks[app_id] = best_hour
    return peaks


def _split_local_hours(a: datetime, b: datetime, tz: int,
                       clamp_start: datetime | None = None,
                       clamp_end: datetime | None = None):
    """把 UTC 区间按「本地小时」切段；可选先裁剪到 [clamp_start, clamp_end)。"""
    if clamp_start is not None:
        a = max(a, clamp_start)
    if clamp_end is not None:
        b = min(b, clamp_end)
    if b <= a:
        return
    cur = _local(a, tz)
    end_local = _local(b, tz)
    while cur < end_local:
        hour_end = cur.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        seg_end = min(end_local, hour_end)
        yield cur.hour, cur, seg_end
        cur = seg_end


# ── /apps/{app_id} ───────────────────────────────────────────

@router.get("/apps/{app_id}")
def app_detail(
    app_id: int,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    tz: int = Query(0, ge=-1440, le=1440),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """单个应用的摘要 + 日趋势 + 时段分布 + Top 窗口（供抽屉展示）。"""
    _require_activity_range(date_from, date_to)
    app = db.query(models.ServerWatchedApplication).filter_by(
        id=app_id, user_id=current_user.id).first()
    if app is None:
        raise HTTPException(status_code=404, detail="应用不存在")

    start_utc, end_utc = business_date_range_to_utc(date_from, date_to, tz)

    daily_rows = db.query(
        models.ServerAppDailyUsage.date,
        func.sum(models.ServerAppDailyUsage.focus_seconds),
        func.sum(models.ServerAppDailyUsage.lifetime_seconds),
    ).filter(
        models.ServerAppDailyUsage.application_id == app_id,
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
    ).group_by(models.ServerAppDailyUsage.date).all()
    by_date = {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in daily_rows}
    series, cursor = [], date_from
    total_focus = total_lifetime = 0
    while cursor <= date_to:
        focus, lifetime = by_date.get(cursor, (0, 0))
        total_focus += focus
        total_lifetime += lifetime
        series.append({"date": cursor.isoformat(), "focusSeconds": focus, "lifetimeSeconds": lifetime})
        cursor += timedelta(days=1)

    hourly = [0] * 24
    windows: dict[str, int] = defaultdict(int)
    hourly_segments: list[list] = [[] for _ in range(24)]
    rows = db.query(
        models.ServerFocusActivity.window_title,
        models.ServerFocusActivity.focus_start_time,
        models.ServerFocusActivity.focus_end_time,
        models.ServerFocusActivity.focus_duration_seconds,
        models.ServerProcessSession.session_start_time,
    ).join(
        models.ServerProcessSession,
        models.ServerProcessSession.id == models.ServerFocusActivity.session_id,
    ).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).filter(
        models.ServerAppUsageSummary.application_id == app_id,
        models.ServerFocusActivity.focus_start_time.isnot(None),
        models.ServerFocusActivity.focus_start_time < end_utc,
        (models.ServerFocusActivity.focus_end_time.is_(None))
        | (models.ServerFocusActivity.focus_end_time > start_utc),
    ).all()
    for title, a, b, dur, sess_start in rows:
        windows[title or "(无标题)"] += int(dur or 0)
        if a is not None and b is not None:
            for hour, seg_start, seg_end in _split_local_hours(a, b, tz, start_utc, end_utc):
                hourly_segments[hour].append((seg_start, seg_end))
    for hour in range(24):
        hourly[hour] = int(_merge_seconds(hourly_segments[hour]))

    top_windows = sorted(windows.items(), key=lambda kv: kv[1], reverse=True)[:10]

    sessions = db.query(models.ServerProcessSession).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).filter(
        models.ServerAppUsageSummary.application_id == app_id,
        models.ServerProcessSession.session_start_time >= start_utc,
        models.ServerProcessSession.session_start_time < end_utc,
    ).order_by(models.ServerProcessSession.session_start_time.desc()).limit(10).all()

    session_count = db.query(func.count(models.ServerProcessSession.id)).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).filter(
        models.ServerAppUsageSummary.application_id == app_id,
        models.ServerProcessSession.session_start_time >= start_utc,
        models.ServerProcessSession.session_start_time < end_utc,
    ).scalar() or 0

    summary_row = db.query(models.ServerAppUsageSummary).filter_by(application_id=app_id).first()
    active_days = db.query(func.count(distinct(models.ServerAppDailyUsage.date))).filter(
        models.ServerAppDailyUsage.application_id == app_id,
        models.ServerAppDailyUsage.date >= date_from,
        models.ServerAppDailyUsage.date <= date_to,
        (models.ServerAppDailyUsage.focus_seconds > 0)
        | (models.ServerAppDailyUsage.lifetime_seconds > 0),
    ).scalar() or 0

    return {
        "appId": app.id,
        "executableName": app.executable_name,
        "executablePath": app.executable_path,
        "summary": {
            "focusSeconds": total_focus,
            "lifetimeSeconds": total_lifetime,
            "focusRatio": _ratio(total_focus, total_lifetime),
            "activeDays": int(active_days),
            "sessionCount": int(session_count),
            "avgSessionFocusSeconds": int(total_focus / session_count) if session_count else 0,
            "firstSeenAt": summary_row.first_seen_at if summary_row else None,
            "lastSeenAt": summary_row.last_seen_end_at if summary_row else None,
        },
        "series": series,
        "hourly": hourly,
        "topWindows": [{"windowTitle": t, "focusSeconds": s} for t, s in top_windows],
        "recentSessions": [
            {
                "id": s.id,
                "processName": s.process_name,
                "start": s.session_start_time,
                "end": s.session_end_time,
                "lifetimeSeconds": s.total_lifetime_seconds,
                "focusSeconds": s.total_focus_seconds,
            }
            for s in sessions
        ],
    }


# ── /sessions ────────────────────────────────────────────────

@router.get("/sessions")
def sessions(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    tz: int = Query(0, ge=-1440, le=1440),
    app_id: int | None = Query(None, alias="appId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    order: str = Query("start_desc"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """按业务日期区间查询会话（session_start_time ∈ [start, end)）。"""
    if order != "start_desc":
        raise HTTPException(status_code=400, detail="order 非法")

    start_utc, end_utc = business_date_range_to_utc(date_from, date_to, tz)
    base = db.query(models.ServerProcessSession).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppUsageSummary.application_id,
    ).filter(
        models.ServerWatchedApplication.user_id == current_user.id,
        models.ServerProcessSession.session_start_time >= start_utc,
        models.ServerProcessSession.session_start_time < end_utc,
    )
    if app_id is not None:
        base = base.filter(models.ServerAppUsageSummary.application_id == app_id)

    total = base.with_entities(func.count(models.ServerProcessSession.id)).scalar() or 0
    rows = base.order_by(models.ServerProcessSession.session_start_time.desc()).offset(
        (page - 1) * page_size).limit(page_size).all()

    ids = [s.id for s in rows]
    counts = {}
    if ids:
        counts = dict(db.query(
            models.ServerFocusActivity.session_id,
            func.count(models.ServerFocusActivity.id),
        ).filter(models.ServerFocusActivity.session_id.in_(ids)).group_by(
            models.ServerFocusActivity.session_id).all())

    app_names = {}
    if rows:
        app_ids = {s.summary.application_id for s in rows}
        app_names = {a.id: a.executable_name for a in db.query(
            models.ServerWatchedApplication).filter(
            models.ServerWatchedApplication.id.in_(app_ids)).all()}

    items = []
    for s in rows:
        app_id_v = s.summary.application_id
        items.append({
            "id": s.id,
            "appId": app_id_v,
            "executableName": app_names.get(app_id_v, ""),
            "processName": s.process_name,
            "start": s.session_start_time,
            "end": s.session_end_time,
            "lifetimeSeconds": s.total_lifetime_seconds,
            "focusSeconds": s.total_focus_seconds,
            "activityCount": int(counts.get(s.id, 0)),
        })
    return {"total": int(total), "page": page, "pageSize": page_size, "items": items}


@router.get("/sessions/{session_id}/activities")
def session_activities(
    session_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """某个会话的窗口活动明细（展开用）。"""
    session = db.query(models.ServerProcessSession).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppUsageSummary.application_id,
    ).filter(
        models.ServerProcessSession.id == session_id,
        models.ServerWatchedApplication.user_id == current_user.id,
    ).first()
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    rows = db.query(models.ServerFocusActivity).filter_by(session_id=session_id).order_by(
        models.ServerFocusActivity.focus_start_time).all()
    return [
        {
            "windowTitle": a.window_title,
            "start": a.focus_start_time,
            "end": a.focus_end_time,
            "durationSeconds": a.focus_duration_seconds,
        }
        for a in rows
    ]


# ── /activity/hourly, /activity/heatmap ──────────────────────

@router.get("/activity/hourly")
def activity_hourly(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    tz: int = Query(0, ge=-1440, le=1440),
    metric: str = Query("focus"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """24 小时分布。focus=活动区间并集；opens=session 开始次数；closes=session 结束次数。"""
    _require_activity_range(date_from, date_to)
    if metric not in ("focus", "opens", "closes"):
        raise HTTPException(status_code=400, detail="metric 非法")

    start_utc, end_utc = business_date_range_to_utc(date_from, date_to, tz)
    out = [0] * 24

    if metric in ("opens", "closes"):
        col = (models.ServerProcessSession.session_start_time if metric == "opens"
               else models.ServerProcessSession.session_end_time)
        rows = db.query(col).join(
            models.ServerAppUsageSummary,
            models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
        ).join(
            models.ServerWatchedApplication,
            models.ServerWatchedApplication.id == models.ServerAppUsageSummary.application_id,
        ).filter(
            models.ServerWatchedApplication.user_id == current_user.id,
            col >= start_utc,
            col < end_utc,
        ).all()
        for (ts,) in rows:
            out[_local(ts, tz).hour] += 1
        return out

    rows = db.query(
        models.ServerFocusActivity.focus_start_time,
        models.ServerFocusActivity.focus_end_time,
    ).join(
        models.ServerProcessSession,
        models.ServerProcessSession.id == models.ServerFocusActivity.session_id,
    ).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppUsageSummary.application_id,
    ).filter(
        models.ServerWatchedApplication.user_id == current_user.id,
        models.ServerFocusActivity.focus_start_time.isnot(None),
        models.ServerFocusActivity.focus_end_time.isnot(None),
        models.ServerFocusActivity.focus_start_time < end_utc,
        models.ServerFocusActivity.focus_end_time > start_utc,
    ).all()

    segments: list[list] = [[] for _ in range(24)]
    for a, b in rows:
        for hour, seg_start, seg_end in _split_local_hours(a, b, tz, start_utc, end_utc):
            segments[hour].append((seg_start, seg_end))
    for hour in range(24):
        out[hour] = int(_merge_seconds(segments[hour]))
    return out


@router.get("/activity/heatmap")
def activity_heatmap(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    tz: int = Query(0, ge=-1440, le=1440),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """7×24 专注热力图（本地星期 × 小时，单位秒；周一为第 0 行）。"""
    _require_activity_range(date_from, date_to)

    start_utc, end_utc = business_date_range_to_utc(date_from, date_to, tz)
    rows = db.query(
        models.ServerFocusActivity.focus_start_time,
        models.ServerFocusActivity.focus_end_time,
    ).join(
        models.ServerProcessSession,
        models.ServerProcessSession.id == models.ServerFocusActivity.session_id,
    ).join(
        models.ServerAppUsageSummary,
        models.ServerAppUsageSummary.id == models.ServerProcessSession.summary_id,
    ).join(
        models.ServerWatchedApplication,
        models.ServerWatchedApplication.id == models.ServerAppUsageSummary.application_id,
    ).filter(
        models.ServerWatchedApplication.user_id == current_user.id,
        models.ServerFocusActivity.focus_start_time.isnot(None),
        models.ServerFocusActivity.focus_end_time.isnot(None),
        models.ServerFocusActivity.focus_start_time < end_utc,
        models.ServerFocusActivity.focus_end_time > start_utc,
    ).all()

    buckets: list[list[list]] = [[[] for _ in range(24)] for _ in range(7)]
    for a, b in rows:
        for hour, seg_start, seg_end in _split_local_hours(a, b, tz, start_utc, end_utc):
            buckets[seg_start.weekday()][hour].append((seg_start, seg_end))

    return [
        [int(_merge_seconds(buckets[day][hour])) for hour in range(24)]
        for day in range(7)
    ]
