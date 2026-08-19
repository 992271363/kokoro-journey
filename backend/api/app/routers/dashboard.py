from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, date, timedelta
from typing import List

from .. import database, models, auth, schemas

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get("/stats", response_model=schemas.DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """获取仪表盘顶部的统计卡片数据"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_focus_seconds = db.query(func.sum(models.ServerProcessSession.total_focus_seconds))\
        .join(models.ServerAppUsageSummary)\
        .join(models.ServerWatchedApplication)\
        .filter(models.ServerWatchedApplication.user_id == current_user.id)\
        .filter(models.ServerProcessSession.session_start_time >= today_start)\
        .scalar() or 0

    # 2. 总计追踪应用数
    total_apps = db.query(models.ServerWatchedApplication)\
        .filter(models.ServerWatchedApplication.user_id == current_user.id)\
        .count()

    # 3. 今日最常用应用 (按专注时间排序)
    # 查询今日 Session，按 App 分组，求和 Focus 时间，取第一名
    most_used = db.query(
        models.ServerWatchedApplication.executable_name,
        func.sum(models.ServerProcessSession.total_focus_seconds).label("today_focus")
    ).select_from(models.ServerWatchedApplication)\
     .join(models.ServerAppUsageSummary)\
     .join(models.ServerProcessSession)\
     .filter(models.ServerWatchedApplication.user_id == current_user.id)\
     .filter(models.ServerProcessSession.session_start_time >= today_start)\
     .group_by(models.ServerWatchedApplication.id)\
     .order_by(desc("today_focus"))\
     .first()
    
    most_used_app_name = most_used[0] if most_used else "暂无数据"
    # 4. 本周总运行时长
    week_start = today_start - timedelta(days=today_start.weekday()) # 本周一
    week_lifetime = db.query(func.sum(models.ServerProcessSession.total_lifetime_seconds))\
        .join(models.ServerAppUsageSummary)\
        .join(models.ServerWatchedApplication)\
        .filter(models.ServerWatchedApplication.user_id == current_user.id)\
        .filter(models.ServerProcessSession.session_start_time >= week_start)\
        .scalar() or 0

    return {
        "today_focus_seconds": int(today_focus_seconds),
        "total_apps_tracked": total_apps,
        "most_used_app_today": most_used_app_name,
        "this_week_lifetime_seconds": int(week_lifetime)
    }

@router.get("/apps", response_model=List[schemas.TopAppItem])
def get_top_apps(
    limit: int = 10,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """获取应用列表（主内容区）"""
    # 查询属于当前用户的 App，包含 summary 信息
    apps = db.query(models.ServerWatchedApplication)\
        .join(models.ServerAppUsageSummary)\
        .filter(models.ServerWatchedApplication.user_id == current_user.id)\
        .order_by(desc(models.ServerAppUsageSummary.total_focus_time_seconds))\
        .limit(limit)\
        .all()
    
    # 构造返回数据
    result = []
    for app in apps:
        result.append({
            "id": app.id,
            "executable_name": app.executable_name,
            "summary": {
                "last_seen_end_at": app.summary.last_seen_end_at,
                "total_lifetime_seconds": app.summary.total_lifetime_seconds,
                "total_focus_time_seconds": app.summary.total_focus_time_seconds
            }
        })
    return result

@router.get("/recent-activity", response_model=List[schemas.RecentActivityItem])
def get_recent_activity(
    limit: int = 5,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """获取侧边栏的最近活动"""
    sessions = db.query(models.ServerProcessSession)\
        .join(models.ServerAppUsageSummary)\
        .join(models.ServerWatchedApplication)\
        .filter(models.ServerWatchedApplication.user_id == current_user.id)\
        .order_by(desc(models.ServerProcessSession.session_end_time))\
        .limit(limit)\
        .all()

    return [
        {
            "id": s.id,
            "process_name": s.process_name,
            "session_start_time": s.session_start_time,
            "session_end_time": s.session_end_time,
            "total_lifetime_seconds": s.total_lifetime_seconds,
            "total_focus_seconds": s.total_focus_seconds,
        }
        for s in sessions
    ]
