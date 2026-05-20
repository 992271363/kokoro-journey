from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.orm import joinedload

from local_database import SessionLocal
from local_models import WatchedApplication, AppUsageSummary, AppDailyUsage, ProcessSession, FocusActivity
from tracking_service import add_or_get_watched_app
from path_utils import normalize_exe_path


@dataclass
class AppInfo:
    exe_path: str
    launch_path: str
    exe_name: str
    total_focus_seconds: int
    total_lifetime_seconds: int
    last_start_at: str
    first_seen_at: str
    last_start_at_ts: float = 0
    first_seen_at_ts: float = 0
    is_watched: bool = True
    is_path_exist: bool = True


class AppRepository:

    @staticmethod
    def get_all_apps() -> List[AppInfo]:
        """返回所有应用（含未监视），用于主表展示。"""
        db = SessionLocal()
        try:
            apps = db.query(WatchedApplication).options(
                joinedload(WatchedApplication.summary)
            ).all()
            return [
                AppInfo(
                    exe_path=app.executable_path,
                    launch_path=app.launch_path or app.executable_path,
                    exe_name=app.executable_name,
                    total_focus_seconds=app.summary.total_focus_time_seconds if app.summary else 0,
                    total_lifetime_seconds=app.summary.total_lifetime_seconds if app.summary else 0,
                    last_start_at=app.summary.last_seen_start_at.strftime("%Y/%m/%d %H:%M") if app.summary and app.summary.last_seen_start_at else "从未",
                    first_seen_at=app.summary.first_seen_at.strftime("%Y/%m/%d %H:%M") if app.summary and app.summary.first_seen_at else "从未",
                    last_start_at_ts=app.summary.last_seen_start_at.timestamp() if app.summary and app.summary.last_seen_start_at else 0,
                    first_seen_at_ts=app.summary.first_seen_at.timestamp() if app.summary and app.summary.first_seen_at else 0,
                    is_watched=app.is_watched,
                    is_path_exist=app.is_path_exist,
                )
                for app in apps
            ]
        finally:
            db.close()

    @staticmethod
    def get_watched_apps_info() -> List[Tuple[str, str]]:
        """只返回 is_watched=True 的应用，给后台监控器用。"""
        db = SessionLocal()
        try:
            apps = db.query(WatchedApplication).filter_by(is_watched=True).all()
            return [(app.executable_path, app.executable_name) for app in apps]
        finally:
            db.close()

    @staticmethod
    def get_app_by_path(exe_path: str) -> Optional[WatchedApplication]:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            return db.query(WatchedApplication).options(
                joinedload(WatchedApplication.summary)
            ).filter_by(executable_path=exe_path).first()
        finally:
            db.close()

    @staticmethod
    def set_app_watched(exe_path: str, watched: bool) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            app.is_watched = watched
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def unwatch_app(exe_path: str) -> bool:
        return AppRepository.set_app_watched(exe_path, False)

    @staticmethod
    def watch_app(exe_path: str) -> bool:
        return AppRepository.set_app_watched(exe_path, True)

    @staticmethod
    def delete_app_completely(exe_path: str) -> bool:
        """彻底删除应用及其所有历史数据。"""
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            # 手动按依赖顺序删除子表，不依赖 ORM cascade
            db.query(AppDailyUsage).filter_by(application_id=app.id).delete()
            summary = db.query(AppUsageSummary).filter_by(application_id=app.id).first()
            if summary:
                db.query(FocusActivity).filter(
                    FocusActivity.session_id.in_(
                        db.query(ProcessSession.id).filter_by(summary_id=summary.id)
                    )
                ).delete(synchronize_session=False)
                db.query(ProcessSession).filter_by(summary_id=summary.id).delete()
                db.query(AppUsageSummary).filter_by(id=summary.id).delete()
            db.delete(app)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def add_app(exe_path: str, exe_name: str) -> None:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            add_or_get_watched_app(db, exe_path, exe_name)
        finally:
            db.close()

    @staticmethod
    def app_exists(exe_path: str) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            return db.query(WatchedApplication).filter_by(executable_path=exe_path).first() is not None
        finally:
            db.close()
