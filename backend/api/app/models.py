from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Date, Boolean, ForeignKey, UniqueConstraint
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
