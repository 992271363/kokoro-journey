import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from sqlalchemy.orm import joinedload
from sqlalchemy import distinct, func

from db.database import SessionLocal
from db.models import (
    WatchedApplication, AppUsageSummary, AppDailyUsage,
    ProcessSession, FocusActivity, AppGroup, AppGroupAssociation, AppColorTag,
    SaveGame
)
from core.tracker import add_or_get_watched_app
from util.path import normalize_exe_path
from util.format import never_text

# 哨兵：区分「未提供」与「显式设为 None（清空）」
_UNSET = object()


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
                    last_start_at=app.summary.last_seen_start_at.strftime("%Y/%m/%d %H:%M") if app.summary and app.summary.last_seen_start_at else never_text(),
                    first_seen_at=app.summary.first_seen_at.strftime("%Y/%m/%d %H:%M") if app.summary and app.summary.first_seen_at else never_text(),
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
    def get_all_groups() -> List[Tuple[int, str, Optional[str]]]:
        db = SessionLocal()
        try:
            groups = db.query(AppGroup).order_by(AppGroup.sort_order, AppGroup.id).all()
            return [(g.id, g.name, g.color) for g in groups]
        finally:
            db.close()

    @staticmethod
    def set_group_color(group_id: int, color: Optional[str]) -> bool:
        if color is None:
            color = None
        elif color.startswith("#"):
            color = color
        else:
            color = f"#{color}"
        db = SessionLocal()
        try:
            db.query(AppGroup).filter_by(id=group_id).update({"color": color})
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @staticmethod
    def set_groups_order(ordered_ids: List[int]) -> None:
        """按给定 id 顺序持久化分组排序。"""
        if not ordered_ids:
            return
        db = SessionLocal()
        try:
            for idx, gid in enumerate(ordered_ids):
                db.query(AppGroup).filter_by(id=gid).update({"sort_order": idx})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def create_group(name: str) -> Optional[int]:
        db = SessionLocal()
        try:
            existing = db.query(AppGroup).filter_by(name=name).first()
            if existing:
                return None
            max_order = db.query(func.max(AppGroup.sort_order)).scalar() or 0
            group = AppGroup(name=name, sort_order=max_order + 1)
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
    def set_launch_path(exe_path: str, launch_path: str) -> bool:
        """手动修改应用的启动路径（按监控唯一键 executable_path 定位）。"""
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            app.launch_path = launch_path
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def rename_app(exe_path: str, new_name: str) -> bool:
        """按 executable_path 定位，修改 executable_name（纯显示名称）。"""
        exe_path = normalize_exe_path(exe_path)
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=exe_path).first()
            if not app:
                return False
            new_name = new_name.strip()
            if new_name == "" or new_name == app.executable_name.strip():
                return True
            app.executable_name = new_name
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
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

    @staticmethod
    def change_tracking_path(old_path: str, new_path: str) -> Tuple[bool, str]:
        old_path = normalize_exe_path(old_path)
        new_path = normalize_exe_path(new_path)
        if old_path == new_path:
            return True, ""
        db = SessionLocal()
        try:
            app = db.query(WatchedApplication).filter_by(executable_path=old_path).first()
            if not app:
                return False, "??????"
            if db.query(WatchedApplication).filter_by(executable_path=new_path).first():
                return False, "??"
            app.executable_path = new_path
            db.commit()
            _refresh_failed_queues(old_path, new_path)
            return True, ""
        except Exception as e:
            db.rollback()
            return False, str(e)
        finally:
            db.close()


    # ---------------- 云存档：本地条目 ----------------

    @staticmethod
    def get_all_save_games() -> List[SaveGame]:
        db = SessionLocal()
        try:
            return db.query(SaveGame).order_by(SaveGame.id).all()
        finally:
            db.close()

    @staticmethod
    def get_save_game(save_id: int) -> Optional[SaveGame]:
        db = SessionLocal()
        try:
            return db.query(SaveGame).filter_by(id=save_id).first()
        finally:
            db.close()

    @staticmethod
    def create_save_game(name: str, local_path: str,
                         linked_app_path: Optional[str] = None,
                         identifier: Optional[str] = None) -> Optional[SaveGame]:
        db = SessionLocal()
        try:
            now = datetime.datetime.now()
            obj = SaveGame(
                name=name,
                identifier=identifier or name,
                local_path=local_path,
                linked_app_path=linked_app_path,
                created_at=now,
                updated_at=now,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def delete_save_game(save_id: int) -> bool:
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            db.delete(obj)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def update_save_game(save_id: int, name=_UNSET,
                         local_path=_UNSET, linked_app_path=_UNSET,
                         identifier=_UNSET) -> bool:
        """更新条目字段；未传参=不改，显式传 None=清空（如清除关联应用）。"""
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            if name is not _UNSET and name is not None:
                obj.name = name
            if identifier is not _UNSET and identifier is not None:
                obj.identifier = identifier
            if local_path is not _UNSET and local_path is not None:
                obj.local_path = local_path
            if linked_app_path is not _UNSET:
                obj.linked_app_path = linked_app_path
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def set_save_game_server_id(save_id: int, server_id: int) -> bool:
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.server_id = server_id
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def set_save_game_slot(save_id: int, slot: Optional[int]) -> bool:
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.server_slot = slot
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def clear_save_game_server_id(save_id: int) -> bool:
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.server_id = None
            obj.server_slot = None
            obj.last_synced_version = None
            obj.last_synced_at = None
            obj.local_fingerprint = None
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def clear_save_game_slot(save_id: int) -> bool:
        """云端某存档位被删除后，清掉本地对该槽的同步记录（保留与游戏的关联）。"""
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.server_slot = None
            obj.last_synced_version = None
            obj.last_synced_at = None
            obj.local_fingerprint = None
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def mark_save_game_synced(save_id: int, version: int, fingerprint: Optional[str],
                              slot: Optional[int] = None) -> bool:
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.last_synced_version = version
            obj.last_synced_at = datetime.datetime.now()
            obj.local_fingerprint = fingerprint
            if slot is not None:
                obj.server_slot = slot
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    @staticmethod
    def create_bound_save_game(name: str, local_path: str, server_id: int,
                               version: Optional[int], fingerprint: Optional[str],
                               slot: Optional[int] = None,
                               identifier: Optional[str] = None) -> Optional[SaveGame]:
        """创建已关联云端游戏的本地条目（linked_app_path 留空，单事务）。"""
        db = SessionLocal()
        try:
            now = datetime.datetime.now()
            obj = SaveGame(
                name=name,
                identifier=identifier or name,
                local_path=local_path,
                linked_app_path=None,
                server_id=server_id,
                server_slot=slot,
                last_synced_version=version,
                last_synced_at=now,
                local_fingerprint=fingerprint,
                created_at=now,
                updated_at=now,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
            return obj
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def bind_save_game_to_server(save_id: int, server_id: int,
                                 version: Optional[int], fingerprint: Optional[str],
                                 slot: Optional[int] = None,
                                 identifier: Optional[str] = None) -> bool:
        """把已有本地条目关联到云端游戏并写入同步状态（不改本地路径与文件）。"""
        db = SessionLocal()
        try:
            obj = db.query(SaveGame).filter_by(id=save_id).first()
            if not obj:
                return False
            obj.server_id = server_id
            if identifier:
                obj.identifier = identifier
            obj.last_synced_version = version
            obj.last_synced_at = datetime.datetime.now()
            obj.local_fingerprint = fingerprint
            if slot is not None:
                obj.server_slot = slot
            obj.updated_at = datetime.datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()


def _refresh_failed_queues(old_path: str, new_path: str) -> None:
    try:
        from core.monitor import _load_failed_queue, _save_failed_queue, _load_dead_queue, _save_dead_queue
    except Exception:
        return
    old_norm = normalize_exe_path(old_path)
    new_norm = normalize_exe_path(new_path)
    for loader, saver in [(_load_failed_queue, _save_failed_queue), (_load_dead_queue, _save_dead_queue)]:
        try:
            queue = loader()
        except Exception:
            continue
        changed = False
        for item in queue:
            if item.get("executable_path") == old_norm:
                item["executable_path"] = new_norm
                changed = True
        if changed:
            try:
                saver(queue)
            except Exception:
                pass
