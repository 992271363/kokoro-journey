"""从 process_sessions / focus_activities 重建 app_daily_usage。

app_daily_usage 是派生汇总表，唯一权威来源是：
- process_sessions.session_start_time / session_end_time  -> lifetime_seconds
- focus_activities.focus_start_time / focus_end_time      -> focus_seconds

历史问题：导入路径（db/io.py）曾直接从 JSON 写 app_daily_usage，而会话按
summary_id + session_start_time 去重，两边不对称，导致汇总表出现大量"孤儿行"
（有日统计、无任何会话），统计界面因此显示出不可能的时长。

本模块按自然日裁剪真实区间后替换汇总表。默认保留无源区间的遗留行
（旧版本只记录了时长、没有会话明细，删掉就等于丢历史）。
tracker.py 的增量写入保持原样（已验证正确），本模块用于一次性修复与导入后重算。
"""
import datetime
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import AppDailyUsage, AppUsageSummary, FocusActivity, ProcessSession

Day = datetime.date
Bucket = Dict[Tuple[int, Day], int]


def _day_start(day: Day) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(0, 0, 0))


def _add_interval(buckets: Bucket, app_id: int,
                  start: datetime.datetime, end: datetime.datetime) -> None:
    """按自然日裁剪区间后累加时长（跨午夜自动拆分到各天）。"""
    if end <= start:
        return
    day = start.date()
    last_day = end.date()
    while day <= last_day:
        seg_start = max(start, _day_start(day))
        seg_end = min(end, _day_start(day + datetime.timedelta(days=1)))
        if seg_end > seg_start:
            key = (app_id, day)
            buckets[key] = buckets.get(key, 0) + int(
                (seg_end - seg_start).total_seconds())
        day += datetime.timedelta(days=1)


def rebuild_app_daily_usage(db: Optional[Session] = None,
                            application_ids: Optional[Iterable[int]] = None,
                            keep_legacy: bool = True) -> dict:
    """重建日统计汇总表。

    db: 可选会话。传入时只 flush 不 commit（由调用方控制事务）；
        不传时自建会话并 commit。
    application_ids: 可选应用范围。传入时只处理这些应用。
    keep_legacy: True（默认）时只重算源区间覆盖到的 (app, date)，
        无源区间的遗留行原样保留；False 时删除范围内全部行做全量重建。

    返回 {"deleted", "written", "legacy_kept", "lifetime_seconds",
          "focus_seconds", "focus_clamped", "legacy_lifetime_seconds",
          "legacy_focus_seconds"}，其中 focus_clamped 是因
    focus_seconds <= lifetime_seconds 约束被裁剪掉的秒数。
    """
    own_db = db is None
    if own_db:
        db = SessionLocal()

    result = {
        "deleted": 0,
        "written": 0,
        "legacy_kept": 0,
        "lifetime_seconds": 0,
        "focus_seconds": 0,
        "focus_clamped": 0,
        "legacy_lifetime_seconds": 0,
        "legacy_focus_seconds": 0,
    }

    try:
        scoped = application_ids is not None
        ids = list(application_ids) if scoped else None
        id_set = set(ids) if scoped else None
        if scoped and not ids:
            return result

        session_q = db.query(
            AppUsageSummary.application_id,
            ProcessSession.session_start_time,
            ProcessSession.session_end_time,
            ProcessSession.total_lifetime_seconds,
        ).join(AppUsageSummary, ProcessSession.summary_id == AppUsageSummary.id)

        focus_q = db.query(
            AppUsageSummary.application_id,
            ProcessSession.session_start_time,
            FocusActivity.focus_start_time,
            FocusActivity.focus_end_time,
            FocusActivity.focus_duration_seconds,
        ).join(ProcessSession, FocusActivity.session_id == ProcessSession.id) \
         .join(AppUsageSummary, ProcessSession.summary_id == AppUsageSummary.id)

        if ids is not None:
            session_q = session_q.filter(AppUsageSummary.application_id.in_(ids))
            focus_q = focus_q.filter(AppUsageSummary.application_id.in_(ids))

        lifetime: Bucket = {}
        for app_id, start, end, secs in session_q.all():
            if start is None:
                continue
            if end is None:
                end = start + datetime.timedelta(seconds=secs or 0)
            _add_interval(lifetime, app_id, start, end)

        focus: Bucket = {}
        for app_id, sess_start, fstart, fend, secs in focus_q.all():
            if fstart is not None and fend is not None:
                _add_interval(focus, app_id, fstart, fend)
            elif secs and sess_start is not None:
                # 旧格式焦点活动无起止时间：挂到所属会话的日期上
                key = (app_id, sess_start.date())
                focus[key] = focus.get(key, 0) + int(secs)

        covered = set(lifetime) | set(focus)

        existing_rows = db.query(
            AppDailyUsage.id,
            AppDailyUsage.application_id,
            AppDailyUsage.date,
            AppDailyUsage.lifetime_seconds,
            AppDailyUsage.focus_seconds,
        ).all()
        if scoped:
            existing_rows = [r for r in existing_rows if r.application_id in id_set]

        if keep_legacy:
            to_delete = [r for r in existing_rows
                         if (r.application_id, r.date) in covered]
            legacy_rows = [r for r in existing_rows
                           if (r.application_id, r.date) not in covered]
            result["legacy_kept"] = len(legacy_rows)
            result["legacy_lifetime_seconds"] = sum(
                r.lifetime_seconds or 0 for r in legacy_rows)
            result["legacy_focus_seconds"] = sum(
                r.focus_seconds or 0 for r in legacy_rows)
        else:
            to_delete = existing_rows

        result["deleted"] = len(to_delete)
        if to_delete:
            db.query(AppDailyUsage).filter(
                AppDailyUsage.id.in_([r.id for r in to_delete])
            ).delete(synchronize_session=False)

        for app_id, day in sorted(covered):
            if scoped and app_id not in id_set:
                continue
            life = lifetime.get((app_id, day), 0)
            foc = focus.get((app_id, day), 0)
            if foc > life:
                result["focus_clamped"] += foc - life
                foc = life
            if life <= 0 and foc <= 0:
                continue
            db.add(AppDailyUsage(
                application_id=app_id,
                date=day,
                lifetime_seconds=life,
                focus_seconds=foc,
            ))
            result["written"] += 1
            result["lifetime_seconds"] += life
            result["focus_seconds"] += foc

        if own_db:
            db.commit()
        else:
            db.flush()
        return result

    except Exception:
        db.rollback()
        raise
    finally:
        if own_db:
            db.close()
