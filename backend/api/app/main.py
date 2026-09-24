from typing import List
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from . import models, schemas, auth, database
from .routers import dashboard, saves, settings, analytics
from .logger import logger


def ensure_aware_dt(dt: datetime) -> datetime:
    """如果 datetime 是 naive（无时区），则假定为 UTC 并添加时区信息"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_start_time(dt: datetime) -> datetime:
    """把会话起始时间归一到 UTC 秒精度，作为幂等业务键 (summary_id, session_start_time)。

    客户端带微秒上传，而数据库列为秒精度；统一到整秒后才能稳定地做存在性判断。
    """
    dt = ensure_aware_dt(dt)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0)

# ── 启动时幂等补列/补索引 ──────────────────────────────────────────────
# create_all 只会新建“缺失的表”，不会给已存在的旧表加列。历史版本新增过
# 若干列（slot / identifier / bg_*），老库缺列时任何 SELECT 都会 500。
# 这里在启动时对已知新增项做一次幂等的 ADD COLUMN / CREATE INDEX，失败仅告警。
_COLUMN_MIGRATIONS = (
    ("server_save_versions", "slot",
     "ALTER TABLE server_save_versions ADD COLUMN slot INT NULL"),
    ("server_save_games", "identifier",
     "ALTER TABLE server_save_games ADD COLUMN identifier VARCHAR(64) NULL"),
    ("server_watched_applications", "launch_with_le",
     "ALTER TABLE server_watched_applications ADD COLUMN launch_with_le "
     "BOOLEAN NOT NULL DEFAULT 0"),
    ("user_preferences", "bg_mode",
     "ALTER TABLE user_preferences ADD COLUMN bg_mode VARCHAR(16) NOT NULL DEFAULT 'auto'"),
    ("user_preferences", "bg_dim",
     "ALTER TABLE user_preferences ADD COLUMN bg_dim INT NULL"),
    ("user_preferences", "bg_blur",
     "ALTER TABLE user_preferences ADD COLUMN bg_blur INT NULL"),
    ("user_preferences", "bg_fit",
     "ALTER TABLE user_preferences ADD COLUMN bg_fit VARCHAR(16) NOT NULL DEFAULT 'cover'"),
)

_INDEX_MIGRATIONS = (
    ("server_save_versions", "ix_server_save_version_game_slot",
     "CREATE INDEX ix_server_save_version_game_slot "
     "ON server_save_versions (game_id, slot)"),
    ("server_save_games", "uix_server_save_game_user_identifier",
     "CREATE UNIQUE INDEX uix_server_save_game_user_identifier "
     "ON server_save_games (user_id, identifier)"),
    # 活动分析：closes 分桶 / activities 区间查询
    ("server_process_sessions", "ix_server_session_summary_end",
     "CREATE INDEX ix_server_session_summary_end "
     "ON server_process_sessions (summary_id, session_end_time)"),
    ("server_focus_activities", "ix_server_focus_activity_session_start",
     "CREATE INDEX ix_server_focus_activity_session_start "
     "ON server_focus_activities (session_id, focus_start_time)"),
)

# 用名称回填 identifier（SUBSTR 在 MySQL/MariaDB 与 SQLite 均可用）
_IDENTIFIER_BACKFILL = (
    "UPDATE server_save_games SET identifier = SUBSTR(name, 1, 64) "
    "WHERE identifier IS NULL OR identifier = ''"
)


def _column_names(inspector, table: str) -> set:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except Exception:
        return set()


def _index_names(inspector, table: str) -> set:
    names = set()
    try:
        names.update(i.get("name") for i in inspector.get_indexes(table))
    except Exception:
        pass
    try:
        names.update(u.get("name") for u in inspector.get_unique_constraints(table))
    except Exception:
        pass
    return {n for n in names if n}


def ensure_schema(engine=None) -> None:
    """幂等地补齐历史新增列与索引；任何失败只告警，不阻断启动。"""
    eng = engine if engine is not None else database.engine
    try:
        inspector = inspect(eng)
        tables = set(inspector.get_table_names())
    except Exception as e:  # 数据库不可用等情况
        logger.warning(f"[ensure_schema] 无法检查数据库结构：{e}")
        return

    for table, column, ddl in _COLUMN_MIGRATIONS:
        if table not in tables or column in _column_names(inspector, table):
            continue
        try:
            with eng.begin() as conn:
                conn.execute(text(ddl))
            logger.info(f"[ensure_schema] 已补列 {table}.{column}")
        except Exception as e:
            logger.warning(f"[ensure_schema] 补列 {table}.{column} 失败：{e}")
        inspector = inspect(eng)

    # identifier 回填（仅影响空值）
    if "server_save_games" in tables and "identifier" in _column_names(
            inspector, "server_save_games"):
        try:
            with eng.begin() as conn:
                conn.execute(text(_IDENTIFIER_BACKFILL))
        except Exception as e:
            logger.warning(f"[ensure_schema] identifier 回填失败：{e}")

    for table, index, ddl in _INDEX_MIGRATIONS:
        if table not in tables or index in _index_names(inspector, table):
            continue
        try:
            with eng.begin() as conn:
                conn.execute(text(ddl))
            logger.info(f"[ensure_schema] 已补索引 {index}")
        except Exception as e:
            logger.warning(f"[ensure_schema] 补索引 {index} 失败：{e}")
        inspector = inspect(eng)


# 初始化数据库表
models.Base.metadata.create_all(bind=database.engine)
ensure_schema()

app = FastAPI(title="Kokoro Journey API")
app.include_router(dashboard.router)
app.include_router(saves.router)
app.include_router(settings.router)
app.include_router(analytics.router)
logger.info("后端 API 已启动。")

#智能同步接口(采用手动事务控制)
@app.post("/sync/sessions/", status_code=status.HTTP_201_CREATED, tags=["Sync"])
def sync_sessions_from_client(
    sessions_data: List[schemas.SyncProcessSession],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not sessions_data:
        return {"message": "无新数据需要同步。"}
        
    try:

        for session_dto in sessions_data:
            #查找或创建WatchedApplication：优先按 uid 匹配，找不到再按 executable_path 兜底（兼容旧数据）
            watched_app = db.query(models.ServerWatchedApplication).filter_by(
                user_id=current_user.id,
                uid=session_dto.uid
            ).first()
            if not watched_app:
                watched_app = db.query(models.ServerWatchedApplication).filter_by(
                    user_id=current_user.id,
                    executable_path=session_dto.executable_path
                ).first()
            if not watched_app:
                watched_app = models.ServerWatchedApplication(
                    owner=current_user,
                    uid=session_dto.uid,
                    executable_name=session_dto.executable_name,
                    executable_path=session_dto.executable_path
                )
                db.add(watched_app)
                db.flush()

            #更新应用完整元数据
            watched_app.uid = session_dto.uid
            watched_app.executable_name = session_dto.executable_name
            watched_app.executable_path = session_dto.executable_path
            watched_app.launch_path = session_dto.launch_path
            watched_app.is_watched = session_dto.is_watched
            watched_app.is_process_path_different = session_dto.is_process_path_different
            watched_app.is_path_exist = session_dto.is_path_exist
            watched_app.launch_with_le = session_dto.launch_with_le

            #锁定并更新或创建AppUsageSummary
            summary = db.query(models.ServerAppUsageSummary).filter_by(
                application_id=watched_app.id
            ).with_for_update().first()

            #current_session_focus_seconds = sum(act.focus_duration_seconds for act in session_dto.activities)
            current_session_focus_seconds = session_dto.total_focus_seconds
            start_time = normalize_start_time(session_dto.session_start_time)
            end_time = ensure_aware_dt(session_dto.session_end_time)

            # 幂等去重：业务键 (summary_id, session_start_time)；已存在则整条跳过，
            # 不新增 session、不累加 summary、不写 activities。
            # 采用 ±1 秒窗口，兼容历史行可能因库精度产生的四舍五入/截断差异。
            if summary is not None:
                existing = db.query(models.ServerProcessSession).filter(
                    models.ServerProcessSession.summary_id == summary.id,
                    models.ServerProcessSession.session_start_time >= start_time - timedelta(seconds=1),
                    models.ServerProcessSession.session_start_time < start_time + timedelta(seconds=1),
                ).first()
                if existing is not None:
                    logger.info(
                        f"跳过重复会话: summary_id={summary.id}, start={start_time.isoformat()}"
                    )
                    continue

            if not summary:
                summary = models.ServerAppUsageSummary(
                    application=watched_app,
                    first_seen_at=start_time,
                    last_seen_start_at=start_time,
                    last_seen_end_at=end_time,
                    total_lifetime_seconds=session_dto.total_lifetime_seconds,
                    total_focus_time_seconds=current_session_focus_seconds
                )
                db.add(summary)
                db.flush()
            else:
                summary.total_lifetime_seconds += session_dto.total_lifetime_seconds
                summary.total_focus_time_seconds += current_session_focus_seconds
                summary.last_seen_start_at = start_time
                summary.last_seen_end_at = end_time
                if not summary.first_seen_at or ensure_aware_dt(summary.first_seen_at) > start_time:
                    summary.first_seen_at = start_time

            #创建ProcessSession
            new_session = models.ServerProcessSession(
                summary_id=summary.id,
                process_name=session_dto.process_name,
                session_start_time=start_time,
                session_end_time=end_time,
                total_lifetime_seconds=session_dto.total_lifetime_seconds,
                total_focus_seconds=current_session_focus_seconds
            )
            db.add(new_session)
            db.flush()

            #批量创建FocusActivities
            activities_to_add = []
            for activity_data in session_dto.activities:
                activities_to_add.append(
                    models.ServerFocusActivity(
                        session_id=new_session.id,
                        window_title=activity_data.window_title,
                        focus_start_time=ensure_aware_dt(activity_data.focus_start_time),
                        focus_end_time=ensure_aware_dt(activity_data.focus_end_time),
                        focus_duration_seconds=activity_data.focus_duration_seconds
                    )
                )
            if activities_to_add:
                db.add_all(activities_to_add)
        
        #所有循环成功结束后，在 try 块的最后，手动提交整个事务
        db.commit()
        logger.info(f"用户 {current_user.username} 成功同步了 {len(sessions_data)} 个会话。")
        return {"message": f"成功同步了 {len(sessions_data)} 个会话。"}

    except Exception as e:
        #如果 try块中的任何地方（包括flush）发生异常手动回滚所有更改
        db.rollback()
        logger.error(f"同步过程中发生严重错误，事务已回滚: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步失败，服务器内部错误: {str(e)}"
        )


#每日统计同步接口
@app.post("/sync/daily/", status_code=status.HTTP_201_CREATED, tags=["Sync"])
def sync_daily_from_client(
    daily_data: List[schemas.SyncAppDailyUsage],
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not daily_data:
        return {"message": "无每日数据需要同步。"}
    try:
        for d in daily_data:
            watched_app = db.query(models.ServerWatchedApplication).filter_by(
                user_id=current_user.id,
                uid=d.uid
            ).first()
            if not watched_app:
                continue
            existing = db.query(models.ServerAppDailyUsage).filter_by(
                application_id=watched_app.id,
                date=d.date
            ).first()
            if existing:
                existing.lifetime_seconds = d.lifetime_seconds
                existing.focus_seconds = d.focus_seconds
            else:
                db.add(models.ServerAppDailyUsage(
                    application_id=watched_app.id,
                    date=d.date,
                    lifetime_seconds=d.lifetime_seconds,
                    focus_seconds=d.focus_seconds
                ))
        db.commit()
        logger.info(f"用户 {current_user.username} 成功同步了 {len(daily_data)} 条每日统计。")
        return {"message": f"成功同步了 {len(daily_data)} 条每日统计。"}
    except Exception as e:
        db.rollback()
        logger.error(f"每日统计同步失败，事务已回滚: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"每日同步失败，服务器内部错误: {str(e)}"
        )


# 为客户端程序提供获取令牌的API
@app.post("/auth/token", response_model=dict, tags=["API Authentication"])
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.warning(f"登录失败: 用户名或密码不正确 (username={form_data.username})")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    logger.info(f"用户 {user.username} 登录成功。")
    return {"access_token": access_token, "token_type": "bearer"}

# 用户注册API
@app.post("/auth/register", response_model=schemas.User, tags=["API Authentication"])
def register_user(user_create: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user_create.username).first()
    if db_user:
        logger.warning(f"注册失败: 用户名已存在 (username={user_create.username})")
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    new_user = auth.create_user(db=db, user=user_create)
    logger.info(f"新用户注册成功: {new_user.username}")
    return new_user
