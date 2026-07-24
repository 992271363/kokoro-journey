import datetime
from sqlalchemy.orm import Session
from db.models import (WatchedApplication, AppUsageSummary,
                            ProcessSession, FocusActivity, AppDailyUsage, AppGroup)
from util.path import normalize_exe_path


def add_or_get_watched_app(db: Session, executable_path: str, executable_name: str):
    """
    检查一个应用是否已被监视。
    如果未监视，创建新记录；如果已存在，恢复监视并返回。
    同时保证每个应用都有一条 AppUsageSummary。
    """
    executable_path = normalize_exe_path(executable_path)

    watched_app = db.query(WatchedApplication).filter(
        WatchedApplication.executable_path == executable_path
    ).first()

    if watched_app:
        watched_app.executable_name = executable_name
        watched_app.is_watched = True
        if not watched_app.launch_path:
            watched_app.launch_path = executable_path

        summary = db.query(AppUsageSummary).filter(
            AppUsageSummary.application_id == watched_app.id
        ).first()
        if not summary:
            summary = AppUsageSummary(
                application_id=watched_app.id,
            )
            db.add(summary)

        db.commit()
        db.refresh(watched_app)
        return watched_app

    new_watched_app = WatchedApplication(
        executable_name=executable_name,
        executable_path=executable_path,
        launch_path=executable_path,
        is_watched=True,
    )
    db.add(new_watched_app)
    db.flush()

    summary = AppUsageSummary(
        application_id=new_watched_app.id,
    )
    db.add(summary)

    db.commit()
    db.refresh(new_watched_app)
    return new_watched_app


def record_process_session(
    db: Session,
    executable_path: str,
    executable_name: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    focus_details: dict
):
    """
    当一个被监视的进程结束时，调用此函数。
    它会创建一条 ProcessSession 记录，并在其下创建多条 FocusActivity 记录，
    最后更新总账 AppUsageSummary。
    """
    print(f"[Tracking Service] 正在为 '{executable_name}' @ '{executable_path}' 记录一个新会话...")

    executable_path = normalize_exe_path(executable_path)

    # 1. 获取或创建应用，并确保应用有 summary
    watched_app = add_or_get_watched_app(db, executable_path, executable_name)

    summary = db.query(AppUsageSummary).filter(
        AppUsageSummary.application_id == watched_app.id
    ).first()
    if not summary:
        summary = AppUsageSummary(
            application_id=watched_app.id,
        )
        db.add(summary)
        db.flush()

    # 2. 计算本次会话的总时长和总焦点时长
    total_lifetime = round((end_time - start_time).total_seconds())
    total_focus_time = round(sum(focus_details.values()))
    if total_lifetime <= 1:
        print(f"[Tracking Service] 会话时长过短 ({total_lifetime}s)，已忽略。")
        return

    # 3. 创建一条新的"会话"记录 (ProcessSession)
    new_session = ProcessSession(
        summary=summary,
        process_name=executable_name,
        session_start_time=start_time,
        session_end_time=end_time,
        total_lifetime_seconds=total_lifetime,
        total_focus_seconds=total_focus_time
    )
    db.add(new_session)
    print(f"[Tracking Service] -> 已创建会话记录: {start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}")

    # 4. 在"会话"下为每个窗口标题创建"焦点活动"记录 (FocusActivity)
    if not focus_details:
        print("[Tracking Service] -> 该会话没有检测到焦点活动。")
    else:
        print(f"[Tracking Service] -> 该会话检测到 {len(focus_details)} 个窗口标题活动...")
        for title, focus_seconds in focus_details.items():
            focus_seconds_int = int(focus_seconds)
            if focus_seconds_int > 0:
                activity = FocusActivity(
                    session=new_session,
                    window_title=title,
                    focus_duration_seconds=focus_seconds_int
                )
                db.add(activity)
                print(f"[Tracking Service]     - 焦点活动: '{title}' ({focus_seconds}s)")

    # 5. 更新总账 (AppUsageSummary)
    summary.total_lifetime_seconds = (summary.total_lifetime_seconds or 0) + total_lifetime
    summary.total_focus_time_seconds = (summary.total_focus_time_seconds or 0) + total_focus_time
    if not summary.first_seen_at:
        summary.first_seen_at = start_time
    summary.last_seen_start_at = start_time
    summary.last_seen_end_at = end_time

    print(f"[Tracking Service] -> 正在更新总账: lifetime +{total_lifetime}s, focus +{total_focus_time}s")

    # 6. 更新每日统计 (AppDailyUsage)，支持跨午夜分片
    date_lifetime_map = {}
    cur = start_time
    while cur.date() < end_time.date():
        next_midnight = cur.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        chunk = (next_midnight - cur).total_seconds()
        if chunk > 0:
            date_lifetime_map[cur.date()] = date_lifetime_map.get(cur.date(), 0) + round(chunk)
        cur = next_midnight
    remaining = (end_time - cur).total_seconds()
    if remaining > 0:
        date_lifetime_map[cur.date()] = date_lifetime_map.get(cur.date(), 0) + round(remaining)

    for usage_date, date_lifetime in date_lifetime_map.items():
        date_focus = round(total_focus_time * (date_lifetime / total_lifetime)) if total_lifetime > 0 else 0
        daily = db.query(AppDailyUsage).filter(
            AppDailyUsage.application_id == watched_app.id,
            AppDailyUsage.date == usage_date,
        ).first()
        if not daily:
            daily = AppDailyUsage(
                application_id=watched_app.id,
                date=usage_date,
            )
            db.add(daily)
        daily.lifetime_seconds = (daily.lifetime_seconds or 0) + date_lifetime
        daily.focus_seconds = (daily.focus_seconds or 0) + date_focus
        print(f"[Tracking Service] -> 更新每日统计: {usage_date} lifetime +{date_lifetime}s, focus +{date_focus}s")

    if not date_lifetime_map:
        usage_date = start_time.date()
        daily = db.query(AppDailyUsage).filter(
            AppDailyUsage.application_id == watched_app.id,
            AppDailyUsage.date == usage_date,
        ).first()
        if not daily:
            daily = AppDailyUsage(
                application_id=watched_app.id,
                date=usage_date,
            )
            db.add(daily)
        daily.lifetime_seconds = (daily.lifetime_seconds or 0) + total_lifetime
        daily.focus_seconds = (daily.focus_seconds or 0) + total_focus_time
        print(f"[Tracking Service] -> 更新每日统计: {usage_date} lifetime +{total_lifetime}s, focus +{total_focus_time}s")

    # 7. 提交所有更改
    try:
        db.commit()
        print(f"[Tracking Service] 数据库更新成功！")
    except Exception as e:
        print(f"[Tracking Service] 数据库提交失败: {e}")
        db.rollback()
        raise
