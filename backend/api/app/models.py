from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Date, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from .database import Base

# 用户模型
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)

    # 关系：一个用户可以拥有多个"被监视的应用"
    watched_applications = relationship("ServerWatchedApplication", back_populates="owner", cascade="all, delete-orphan")

#被监视的应用 (顶层模型)
class ServerWatchedApplication(Base):
    __tablename__ = 'server_watched_applications'
    __table_args__ = (
        UniqueConstraint('user_id', 'executable_path', name='uix_user_exec_path'),
        UniqueConstraint('user_id', 'uid', name='uix_user_uid'),
    )

    id = Column(Integer, primary_key=True)
    uid = Column(String(64), nullable=True, index=True)
    executable_name = Column(String(255), nullable=False)
    executable_path = Column(String(512), nullable=False, index=True)
    launch_path = Column(String(512), nullable=True)
    is_process_path_different = Column(Boolean, nullable=False, default=False)
    is_path_exist = Column(Boolean, nullable=False, default=True)
    is_watched = Column(Boolean, nullable=False, default=True)

    # 外键：关联到用户
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 关系：指回它的拥有者
    owner = relationship("User", back_populates="watched_applications")
    # 关系：一个"被监视的应用"对应一个"总账"
    summary = relationship("ServerAppUsageSummary", back_populates="application", uselist=False, cascade="all, delete-orphan")
    # 关系：一个"被监视的应用"对应多条每日统计
    daily_usages = relationship("ServerAppDailyUsage", back_populates="application", cascade="all, delete-orphan")

# 应用使用总账
class ServerAppUsageSummary(Base):
    __tablename__ = 'server_app_usage_summary'
    id = Column(Integer, primary_key=True)

    # 外键：关联到被监视的应用
    application_id = Column(Integer, ForeignKey('server_watched_applications.id'), nullable=False, unique=True)

    first_seen_at = Column(DateTime, nullable=True)
    last_seen_start_at = Column(DateTime, nullable=True)
    last_seen_end_at = Column(DateTime, nullable=True)
    total_lifetime_seconds = Column(Integer, nullable=False, default=0)
    total_focus_time_seconds = Column(Integer, nullable=False, default=0)

    # 关系
    application = relationship("ServerWatchedApplication", back_populates="summary")
    sessions = relationship("ServerProcessSession", back_populates="summary", cascade="all, delete-orphan")

#进程会话
class ServerProcessSession(Base):
    __tablename__ = 'server_process_sessions'
    __table_args__ = (
        UniqueConstraint('summary_id', 'session_start_time',
                         name='uix_server_session_summary_start'),
    )
    id = Column(Integer, primary_key=True)

    # 外键：关联到总账
    summary_id = Column(Integer, ForeignKey('server_app_usage_summary.id'), nullable=False, index=True)

    process_name = Column(String(255), nullable=False)
    session_start_time = Column(DateTime, nullable=False)
    session_end_time = Column(DateTime, nullable=False)
    total_lifetime_seconds = Column(Integer, nullable=False)
    total_focus_seconds = Column(Integer, nullable=False, default=0)

    # 关系
    summary = relationship("ServerAppUsageSummary", back_populates="sessions")
    activities = relationship("ServerFocusActivity", back_populates="session", cascade="all, delete-orphan")

#焦点活动
class ServerFocusActivity(Base):
    __tablename__ = 'server_focus_activities'
    id = Column(Integer, primary_key=True)

    # 外键：关联到会话
    session_id = Column(Integer, ForeignKey('server_process_sessions.id'), nullable=False, index=True)

    window_title = Column(String(1024))
    focus_start_time = Column(DateTime, nullable=True)
    focus_end_time = Column(DateTime, nullable=True)
    focus_duration_seconds = Column(Integer, nullable=False)

    # 关系
    session = relationship("ServerProcessSession", back_populates="activities")

#每日使用统计
class ServerAppDailyUsage(Base):
    __tablename__ = 'server_app_daily_usage'
    __table_args__ = (
        UniqueConstraint('application_id', 'date', name='uix_server_app_daily_app_date'),
    )

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey('server_watched_applications.id'), nullable=False, index=True)
    date = Column(Date, nullable=False)
    lifetime_seconds = Column(BigInteger, nullable=False, default=0)
    focus_seconds = Column(BigInteger, nullable=False, default=0)

    application = relationship("ServerWatchedApplication", back_populates="daily_usages")


# ============================================================
# 云存档
# ============================================================

# 云存档游戏（用户自建：显示名称 + 用户自定义标识符 + 由服务端生成的 id）
class ServerSaveGame(Base):
    __tablename__ = 'server_save_games'
    __table_args__ = (
        # 配对键是标识符（每用户唯一）；显示名称允许重名。
        UniqueConstraint('user_id', 'identifier', name='uix_server_save_game_user_identifier'),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    # 用户自定义标识符：客户端↔云端配对键（1..64，字母/数字/-/_/./中文）。
    identifier = Column(String(64), nullable=False)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    versions = relationship(
        "ServerSaveVersion",
        back_populates="game",
        cascade="all, delete-orphan",
    )
    slot_metas = relationship(
        "ServerSaveSlotMeta",
        back_populates="game",
        cascade="all, delete-orphan",
    )


# 云存档位备注名（用户自定义，独立于版本内容：覆盖/删除槽内容后备注仍保留）
class ServerSaveSlotMeta(Base):
    __tablename__ = 'server_save_slot_metas'
    __table_args__ = (
        UniqueConstraint('game_id', 'slot', name='uix_server_save_slot_meta_game_slot'),
    )

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('server_save_games.id'), nullable=False, index=True)
    slot = Column(Integer, nullable=False)          # 1..SLOT_COUNT
    label = Column(String(32), nullable=False)
    updated_at = Column(DateTime, nullable=True)

    game = relationship("ServerSaveGame", back_populates="slot_metas")


# 云存档版本（整目录完整快照）
class ServerSaveVersion(Base):
    __tablename__ = 'server_save_versions'
    __table_args__ = (
        UniqueConstraint('game_id', 'version_number',
                         name='uix_server_save_version_game_number'),
        # 同一槽位允许同时存在「旧 committed + 新 pending」两行（两阶段写入）；
        # 「每槽至多一条 committed」由 commit_version 覆盖逻辑保证，故此处仅建普通索引。
        Index('ix_server_save_version_game_slot', 'game_id', 'slot'),
    )

    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('server_save_games.id'), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)

    # 存档位（1..SLOT_COUNT）；旧数据迁移前为空。
    slot = Column(Integer, nullable=True)

    status = Column(String(16), nullable=False, default='pending')  # pending | committed
    total_size = Column(BigInteger, nullable=False, default=0)
    file_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=True)

    game = relationship("ServerSaveGame", back_populates="versions")
    files = relationship(
        "ServerSaveFile",
        back_populates="version",
        cascade="all, delete-orphan",
    )


# 云存档文件清单（仅一个 sha256 字段，P1 不建索引/不做去重）
class ServerSaveFile(Base):
    __tablename__ = 'server_save_files'
    __table_args__ = (
        UniqueConstraint('version_id', 'relative_path',
                         name='uix_server_save_file_version_path'),
    )

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey('server_save_versions.id'), nullable=False, index=True)

    relative_path = Column(String(1024), nullable=False)
    size = Column(BigInteger, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    mtime_ns = Column(BigInteger, nullable=True)

    version = relationship("ServerSaveVersion", back_populates="files")


# 云同步活动设备（每个用户仅一个；用于“新设备接管云同步”）
class ServerCloudSession(Base):
    __tablename__ = 'server_cloud_sessions'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    active_device_id = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=True)


# ============================================================
# 用户偏好 / 背景资源
# ============================================================

# 用户偏好（每个用户一行；目前仅背景选择与显示参数）
class UserPreference(Base):
    __tablename__ = 'user_preferences'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True, index=True)
    # 背景选择：'default:BG1'..'default:BG5' 或 'custom:<UserBackground.id>'
    background = Column(String(64), nullable=False, default='default:BG1')

    # 背景显示参数：mode=auto 时前端按图片亮度自动算遮罩/模糊，忽略 dim/blur
    bg_mode = Column(String(16), nullable=False, default='auto')   # auto | manual
    bg_dim = Column(Integer, nullable=True)                        # 0..100（遮罩强度，manual 生效）
    bg_blur = Column(Integer, nullable=True)                       # 0..20 px（manual 生效）
    bg_fit = Column(String(16), nullable=False, default='cover')   # cover | contain

    updated_at = Column(DateTime, nullable=True)


# 用户上传的背景图（每人可多张，图库）
class UserBackground(Base):
    __tablename__ = 'user_backgrounds'
    __table_args__ = (
        UniqueConstraint('user_id', 'filename', name='uix_user_background_user_filename'),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)

    filename = Column(String(255), nullable=False)       # 磁盘文件名（uuid.webp）
    original_name = Column(String(255), nullable=True)   # 上传时的原始文件名（仅展示）
    content_type = Column(String(64), nullable=False, default='image/webp')
    size = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=True)

