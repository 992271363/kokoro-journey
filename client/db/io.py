import os
import json
import shutil
import zipfile
from datetime import datetime
from typing import Optional

from db.database import SessionLocal, db_path
from db.models import (
    WatchedApplication, AppUsageSummary, AppDailyUsage,
    ProcessSession, FocusActivity
)
from util.path import get_data_dir, normalize_exe_path


def _failed_sessions_path() -> str:
    return os.path.join(get_data_dir(), "failed_sessions.json")


def _backup_db() -> str:
    if not os.path.exists(db_path):
        return ""
    data_dir = get_data_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_name = f"local_client_{timestamp}.bak"
    bak_path = os.path.join(data_dir, bak_name)
    shutil.copy2(db_path, bak_path)

    backups = sorted(
        [f for f in os.listdir(data_dir) if f.startswith("local_client_") and f.endswith(".bak")],
        key=lambda x: os.path.getmtime(os.path.join(data_dir, x))
    )
    for old in backups[:-5]:
        os.remove(os.path.join(data_dir, old))

    return bak_path


def export_data(filepath: str, format_type: str) -> tuple[bool, str]:
    if not os.path.exists(db_path):
        return False, "数据库文件不存在"

    if format_type == "db":
        try:
            shutil.copy2(db_path, filepath)
            return True, f"已导出到 {filepath}"
        except Exception as e:
            return False, f"导出失败: {e}"

    elif format_type == "json":
        try:
            data = _build_export_json()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True, f"已导出到 {filepath}"
        except Exception as e:
            return False, f"导出失败: {e}"

    elif format_type == "zip":
        try:
            json_path = filepath.replace(".zip", ".json")
            data = _build_export_json()
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(db_path, "local_client.db")
                zf.write(json_path, "database.json")
            os.remove(json_path)
            return True, f"已导出到 {filepath}"
        except Exception as e:
            return False, f"导出失败: {e}"

    return False, "未知导出格式"


def _build_export_json() -> dict:
    db = SessionLocal()
    try:
        apps = db.query(WatchedApplication).all()
        app_list = []
        total_sessions = 0

        for app in apps:
            summary = app.summary
            daily_list = []
            for d in app.daily_usages:
                daily_list.append({
                    "date": d.date.isoformat(),
                    "focus_hours": round(d.focus_seconds / 3600.0, 2),
                    "lifetime_hours": round(d.lifetime_seconds / 3600.0, 2),
                })

            session_list = []
            if summary:
                for s in summary.sessions:
                    total_sessions += 1
                    activities = []
                    for a in s.activities:
                        activities.append({
                            "window_title": a.window_title,
                            "focus_start_time": a.focus_start_time.isoformat() if a.focus_start_time else None,
                            "focus_end_time": a.focus_end_time.isoformat() if a.focus_end_time else None,
                            "focus_hours": round(a.focus_duration_seconds / 3600.0, 2),
                        })
                    session_list.append({
                        "start_time": s.session_start_time.isoformat(),
                        "end_time": s.session_end_time.isoformat() if s.session_end_time else None,
                        "focus_hours": round(s.total_focus_seconds / 3600.0, 2),
                        "lifetime_hours": round(s.total_lifetime_seconds / 3600.0, 2),
                        "window_activities": activities,
                    })

            app_list.append({
                "uid": app.uid,
                "name": app.executable_name,
                "executable_path": app.executable_path,
                "launch_path": app.launch_path,
                "is_watched": app.is_watched,
                "is_process_path_different": app.is_process_path_different,
                "is_path_exist": app.is_path_exist,
                "total_focus_hours": round(summary.total_focus_time_seconds / 3600.0, 2) if summary else 0.0,
                "total_lifetime_hours": round(summary.total_lifetime_seconds / 3600.0, 2) if summary else 0.0,
                "first_seen": summary.first_seen_at.strftime("%Y-%m-%d %H:%M") if summary and summary.first_seen_at else None,
                "last_seen": summary.last_seen_end_at.strftime("%Y-%m-%d %H:%M") if summary and summary.last_seen_end_at else None,
                "daily_usage": daily_list,
                "sessions": session_list,
            })

        return {
            "export_info": {
                "version": "2.0",
                "exported_at": datetime.now().isoformat(),
                "app_count": len(app_list),
                "total_sessions": total_sessions,
            },
            "applications": app_list,
        }
    finally:
        db.close()


def import_data(filepath: str) -> tuple[bool, str]:
    if not os.path.exists(filepath):
        return False, "文件不存在"

    ext = os.path.splitext(filepath)[1].lower()

    bak = _backup_db()

    try:
        if ext == ".db":
            shutil.copy2(filepath, db_path)
            return True, f"已导入数据库文件（已备份: {bak}）"

        elif ext == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            _import_from_json(data)
            return True, f"已导入 JSON 数据（已备份: {bak}）"

        elif ext == ".zip":
            with zipfile.ZipFile(filepath, "r") as zf:
                names = zf.namelist()
                if "local_client.db" in names:
                    zf.extract("local_client.db", os.path.dirname(db_path))
                    tmp = os.path.join(os.path.dirname(db_path), "local_client.db")
                    if os.path.exists(db_path):
                        os.remove(db_path)
                    os.rename(tmp, db_path)
                    return True, f"已导入 ZIP 中的数据库（已备份: {bak}）"
                elif "database.json" in names:
                    with zf.open("database.json") as f:
                        data = json.load(f)
                    _import_from_json(data)
                    return True, f"已导入 ZIP 中的 JSON（已备份: {bak}）"
                else:
                    return False, "ZIP 中未找到有效的数据文件"

        else:
            return False, f"不支持的文件格式: {ext}"

    except Exception as e:
        return False, f"导入失败: {e}"


def _import_from_json(data: dict) -> None:
    from db.database import engine
    from db.models import Base
    from core.tracker import add_or_get_watched_app
    from core.daily_rebuild import rebuild_app_daily_usage

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for app_data in data.get("applications", []):
            exe_path = normalize_exe_path(app_data["executable_path"])
            exe_name = app_data["name"]
            launch_path = app_data.get("launch_path") or exe_path

            watched_app = add_or_get_watched_app(db, exe_path, exe_name)
            # 应用完整字段（v2.0；旧格式缺省时用默认值）
            if app_data.get("uid"):
                watched_app.uid = app_data["uid"]
            watched_app.launch_path = launch_path
            watched_app.is_watched = app_data.get("is_watched", True)
            watched_app.is_process_path_different = app_data.get("is_process_path_different", False)
            watched_app.is_path_exist = app_data.get("is_path_exist", True)

            summary = db.query(AppUsageSummary).filter_by(application_id=watched_app.id).first()
            if summary:
                summary.total_focus_time_seconds = int(app_data.get("total_focus_hours", 0) * 3600)
                summary.total_lifetime_seconds = int(app_data.get("total_lifetime_hours", 0) * 3600)
                if app_data.get("first_seen"):
                    summary.first_seen_at = datetime.fromisoformat(app_data["first_seen"].replace(" ", "T"))
                if app_data.get("last_seen"):
                    summary.last_seen_end_at = datetime.fromisoformat(app_data["last_seen"].replace(" ", "T"))

            # 日统计不从 JSON 直接写入：app_daily_usage 是派生表，
            # 导入完会话与焦点活动后统一由 rebuild_app_daily_usage 重算，
            # 否则汇总表会与原始区间脱节（历史漂移的根源）。

            # 恢复会话与焦点活动（v2.0 含起止时间；旧格式时间为空）
            if summary:
                for s in app_data.get("sessions", []):
                    start_time = datetime.fromisoformat(s["start_time"]) if s.get("start_time") else None
                    if not start_time:
                        continue
                    session = ProcessSession(
                        summary_id=summary.id,
                        process_name=exe_name,
                        session_start_time=start_time,
                        session_end_time=datetime.fromisoformat(s["end_time"]) if s.get("end_time") else None,
                        total_lifetime_seconds=int(s.get("lifetime_hours", 0) * 3600),
                        total_focus_seconds=int(s.get("focus_hours", 0) * 3600),
                    )
                    db.add(session)
                    db.flush()
                    for a in s.get("window_activities", []):
                        activity = FocusActivity(
                            session_id=session.id,
                            window_title=a.get("window_title", ""),
                            focus_start_time=datetime.fromisoformat(a["focus_start_time"]) if a.get("focus_start_time") else None,
                            focus_end_time=datetime.fromisoformat(a["focus_end_time"]) if a.get("focus_end_time") else None,
                            focus_duration_seconds=int(a.get("focus_hours", 0) * 3600),
                        )
                        db.add(activity)

            db.commit()
        rebuild_app_daily_usage(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def clear_all_data() -> tuple[bool, str]:
    try:
        bak = _backup_db()
        if os.path.exists(db_path):
            os.remove(db_path)
        failed_path = _failed_sessions_path()
        if os.path.exists(failed_path):
            os.remove(failed_path)
        return True, f"已清除所有数据（已备份: {bak}）"
    except Exception as e:
        return False, f"清除失败: {e}"


def clear_failed_queue() -> tuple[bool, str]:
    try:
        failed_path = _failed_sessions_path()
        if os.path.exists(failed_path):
            os.remove(failed_path)
            return True, "已清除失败队列"
        return True, "失败队列为空"
    except Exception as e:
        return False, f"清除失败: {e}"


def preview_import_json(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {"error": "文件不存在"}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"JSON 解析失败: {e}"}

    apps = data.get("applications", [])
    export_info = data.get("export_info", {})
    total_sessions = export_info.get("total_sessions", 0)
    total_daily = sum(len(a.get("daily_usage", [])) for a in apps)

    app_list = []
    for a in apps:
        app_list.append({
            "name": a.get("name", "未知"),
            "path": a.get("executable_path", ""),
            "focus_hours": a.get("total_focus_hours", 0),
            "lifetime_hours": a.get("total_lifetime_hours", 0),
            "daily_count": len(a.get("daily_usage", [])),
            "session_count": len(a.get("sessions", [])),
        })

    return {
        "app_count": len(apps),
        "total_sessions": total_sessions,
        "total_daily": total_daily,
        "apps": app_list,
        "export_info": export_info,
    }


def merge_import_json(filepath: str, dry_run: bool = False,
                      progress_callback=None) -> tuple[bool, dict]:
    from db.database import SessionLocal
    from core.tracker import add_or_get_watched_app
    from core.daily_rebuild import rebuild_app_daily_usage

    if not os.path.exists(filepath):
        return False, {"error": "文件不存在"}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, {"error": f"JSON 解析失败: {e}"}

    apps = data.get("applications", [])
    if not apps:
        return False, {"error": "JSON 中无应用数据"}

    if not dry_run:
        bak = _backup_db()
    else:
        bak = None

    db = SessionLocal()
    try:
        touched_app_ids = set()
        stats = {
            "apps_added": 0,
            "apps_updated": 0,
            "daily_upserted": 0,
            "sessions_added": 0,
            "bak_path": bak or "",
        }

        for i, app_data in enumerate(apps):
            exe_path = normalize_exe_path(app_data.get("executable_path", ""))
            if not exe_path:
                continue

            exe_name = app_data.get("name", "未知")

            existing = db.query(WatchedApplication).filter(
                WatchedApplication.executable_path == exe_path
            ).first()

            if existing:
                app = existing
                stats["apps_updated"] += 1
                if progress_callback:
                    progress_callback(f"[UPDATE] {exe_name}")
            else:
                app = add_or_get_watched_app(db, exe_path, exe_name)
                stats["apps_added"] += 1
                if progress_callback:
                    progress_callback(f"[ADD] {exe_name}")

            # 应用完整字段（v2.0；旧格式缺省时用默认值；uid 仅在缺失时补）
            if app_data.get("uid") and not app.uid:
                app.uid = app_data["uid"]
            if app_data.get("launch_path"):
                app.launch_path = app_data["launch_path"]
            app.is_watched = app_data.get("is_watched", True)
            app.is_process_path_different = app_data.get("is_process_path_different", False)
            app.is_path_exist = app_data.get("is_path_exist", True)

            summary = db.query(AppUsageSummary).filter_by(
                application_id=app.id
            ).first()
            if summary:
                summary.total_focus_time_seconds = int(
                    app_data.get("total_focus_hours", 0) * 3600)
                summary.total_lifetime_seconds = int(
                    app_data.get("total_lifetime_hours", 0) * 3600)
                if app_data.get("first_seen"):
                    summary.first_seen_at = datetime.fromisoformat(
                        app_data["first_seen"].replace(" ", "T"))
                if app_data.get("last_seen"):
                    summary.last_seen_end_at = datetime.fromisoformat(
                        app_data["last_seen"].replace(" ", "T"))

            touched_app_ids.add(app.id)

            # 日统计不从 JSON 直接写入：app_daily_usage 是派生表，
            # 合并完会话与焦点活动后统一由 rebuild_app_daily_usage 重算，
            # 否则汇总表会与原始区间脱节（历史漂移的根源）。

            # 合并会话与焦点活动（按 summary_id + session_start_time 去重）
            if summary:
                for s in app_data.get("sessions", []):
                    start_time = datetime.fromisoformat(s["start_time"]) if s.get("start_time") else None
                    if not start_time:
                        continue
                    exists = db.query(ProcessSession).filter_by(
                        summary_id=summary.id, session_start_time=start_time
                    ).first()
                    if exists:
                        continue
                    session = ProcessSession(
                        summary_id=summary.id,
                        process_name=exe_name,
                        session_start_time=start_time,
                        session_end_time=datetime.fromisoformat(s["end_time"]) if s.get("end_time") else None,
                        total_lifetime_seconds=int(s.get("lifetime_hours", 0) * 3600),
                        total_focus_seconds=int(s.get("focus_hours", 0) * 3600),
                    )
                    db.add(session)
                    db.flush()
                    for a in s.get("window_activities", []):
                        activity = FocusActivity(
                            session_id=session.id,
                            window_title=a.get("window_title", ""),
                            focus_start_time=datetime.fromisoformat(a["focus_start_time"]) if a.get("focus_start_time") else None,
                            focus_end_time=datetime.fromisoformat(a["focus_end_time"]) if a.get("focus_end_time") else None,
                            focus_duration_seconds=int(a.get("focus_hours", 0) * 3600),
                        )
                        db.add(activity)
                    stats["sessions_added"] += 1

            if progress_callback:
                progress_callback(f"[DONE] {exe_name} ({i+1}/{len(apps)})")

        if dry_run:
            db.rollback()
            stats["bak_path"] = ""
            return True, stats

        rebuilt = rebuild_app_daily_usage(db, sorted(touched_app_ids))
        stats["daily_upserted"] = rebuilt["written"]
        stats["focus_clamped"] = rebuilt["focus_clamped"]
        if progress_callback:
            progress_callback(
                f"[REPAIR] 已按会话/焦点区间重算日统计："
                f"写入 {rebuilt['written']} 行，删除 {rebuilt['deleted']} 行")
        db.commit()
        return True, stats

    except Exception as e:
        db.rollback()
        return False, {"error": str(e), "bak_path": bak or ""}
    finally:
        db.close()
