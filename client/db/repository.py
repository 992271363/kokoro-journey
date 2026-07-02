from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.orm import joinedload
from sqlalchemy import distinct

from db.database import SessionLocal
from db.models import (
    WatchedApplication, AppUsageSummary, AppDailyUsage,
    ProcessSession, FocusActivity, AppGroup, AppGroupAssociation, AppColorTag
)
from core.tracker import add_or_get_watched_app
from util.path import normalize_exe_path


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
    group_ids: list = field(default_factory=list)
    color_tags: list = field(default_factory=list)


class AppRepository:

    @staticmethod
    def get_all_apps(group_filter: int = None) -> List[AppInfo]:
        db = SessionLocal()
        try:
            if group_filter is not None:
                app_ids = [
                    a.application_id for a in
                    db.query(AppGroupAssociation).filter_by(group_id=group_filter).all()
                ]
                apps = db.query(WatchedApplication).options(
                    joinedload(WatchedApplication.summary)
                ).filter(WatchedApplication.id.in_(app_ids)).all()
            else:
                apps = db.query(WatchedApplication).options(
                    joinedload(WatchedApplication.summary)
                ).all()

            result = []
            for app in apps:
                group_ids = [g.id for g in app.groups]
                color_tags = [t.color for t in app.color_tags]
                result.append(AppInfo(
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
                    group_ids=group_ids,
                    color_tags=color_tags,
                ))
            return result
        finally:
            db.close()

    @staticmethod
    def get_all_groups() -> List[Tuple[int, str]]:
        db = SessionLocal()
        try:
            groups = db.query(AppGroup).all()
            return [(g.id, g.name) for g in groups]
        finally:
            db.close()

    @staticmethod
    def create_group(name: str) -> Optional[int]:
        db = SessionLocal()
        try:
            existing = db.query(AppGroup).filter_by(name=name).first()
            if existing:
                return None
            group = AppGroup(name=name)
            db.add(group)
            db.commit()
            return group.id
        finally:
            db.close()

    @staticmethod
    def delete_group(group_id: int) -> bool:
        db = SessionLocal()
        try:
            group = db.query(AppGroup).filter_by(id=group_id).first()
            if not group:
                return False
            db.query(AppGroupAssociation).filter_by(group_id=group_id).delete()
            db.delete(group)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def rename_group(group_id: int, new_name: str) -> bool:
        db = SessionLocal()
        try:
            group = db.query(AppGroup).filter_by(id=group_id).first()
            if not group:
                return False
            group.name = new_name
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def set_app_groups(exe_path: str, group_ids: List[int]) -> None:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return
            groups = db.query(AppGroup).filter(AppGroup.id.in_(group_ids)).all()
            app.groups = groups
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_app_groups(exe_path: str) -> List[Tuple[int, str]]:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return []
            return [(g.id, g.name) for g in app.groups]
        finally:
            db.close()

    @staticmethod
    def toggle_app_group(exe_path: str, group_id: int) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            group = db.query(AppGroup).filter_by(id=group_id).first()
            if not app or not group:
                return False
            if group in app.groups:
                app.groups.remove(group)
                db.commit()
                return False
            else:
                app.groups.append(group)
                db.commit()
                return True
        finally:
            db.close()

    @staticmethod
    def add_color_tag(exe_path: str, color: str) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            existing = db.query(AppColorTag).filter_by(
                application_id=app.id, color=color
            ).first()
            if existing:
                return False
            db.add(AppColorTag(application_id=app.id, color=color))
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def remove_color_tag(exe_path: str, color: str) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            tag = db.query(AppColorTag).filter_by(
                application_id=app.id, color=color
            ).first()
            if not tag:
                return False
            db.delete(tag)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def clear_color_tags(exe_path: str) -> bool:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            db.query(AppColorTag).filter_by(application_id=app.id).delete()
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def get_color_tags(exe_path: str) -> List[str]:
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return []
            return [t.color for t in app.color_tags]
        finally:
            db.close()

    @staticmethod
    def get_watched_apps_info() -> List[Tuple[str, str]]:
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
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            db.query(AppColorTag).filter_by(application_id=app.id).delete()
            db.query(AppGroupAssociation).filter_by(application_id=app.id).delete()
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
