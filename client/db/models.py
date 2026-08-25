import uuid

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)

from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


def generate_uid():
    return uuid.uuid4().hex


class WatchedApplication(Base):
    __tablename__ = "watched_applications"

    id = Column(Integer, primary_key=True)
    uid = Column(String, nullable=False, unique=True, default=generate_uid)

    executable_name = Column(String, nullable=False)
    executable_path = Column(String, nullable=False, unique=True, index=True)

    launch_path = Column(String, nullable=True)
    is_process_path_different = Column(Boolean, nullable=False, default=False)
    is_path_exist = Column(Boolean, nullable=False, default=True)
    is_watched = Column(Boolean, nullable=False, default=True)

    summary = relationship(
        "AppUsageSummary",
        back_populates="application",
        uselist=False,
        cascade="all, delete-orphan",
    )

    daily_usages = relationship(
        "AppDailyUsage",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    groups = relationship(
        "AppGroup",
        secondary="app_group_associations",
        back_populates="applications",
    )

    color_tags = relationship(
        "AppColorTag",
        back_populates="application",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<WatchedApplication("
            f"id={self.id}, "
            f"uid='{self.uid}', "
            f"exe='{self.executable_name}', "
            f"path='{self.executable_path}', "
            f"launch_path='{self.launch_path}'"
            f")>"
        )


class AppUsageSummary(Base):
    __tablename__ = "app_usage_summary"

    id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("watched_applications.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    first_seen_at = Column(DateTime, nullable=True)
    last_seen_start_at = Column(DateTime, nullable=True)
    last_seen_end_at = Column(DateTime, nullable=True)

    total_lifetime_seconds = Column(BigInteger, nullable=False, default=0)
    total_focus_time_seconds = Column(BigInteger, nullable=False, default=0)

    application = relationship(
        "WatchedApplication",
        back_populates="summary",
    )

    sessions = relationship(
        "ProcessSession",
        back_populates="summary",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "total_lifetime_seconds >= 0",
            name="ck_summary_lifetime_non_negative",
        ),
        CheckConstraint(
            "total_focus_time_seconds >= 0",
            name="ck_summary_focus_non_negative",
        ),
        CheckConstraint(
            "total_focus_time_seconds <= total_lifetime_seconds",
            name="ck_summary_focus_lte_lifetime",
        ),
    )

    def __repr__(self):
        return (
            f"<AppUsageSummary("
            f"application_id={self.application_id}, "
            f"lifetime={self.total_lifetime_seconds}s, "
            f"focus={self.total_focus_time_seconds}s"
            f")>"
        )


class AppDailyUsage(Base):
    __tablename__ = "app_daily_usage"

    id = Column(Integer, primary_key=True)

    application_id = Column(
        Integer,
        ForeignKey("watched_applications.id"),
        nullable=False,
        index=True,
    )

    date = Column(Date, nullable=False, index=True)

    lifetime_seconds = Column(BigInteger, nullable=False, default=0)
    focus_seconds = Column(BigInteger, nullable=False, default=0)

    synced = Column(Boolean, nullable=False, default=False)

    application = relationship(
        "WatchedApplication",
        back_populates="daily_usages",
    )

    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "date",
            name="uq_app_daily_usage_application_date",
        ),
        CheckConstraint(
            "lifetime_seconds >= 0",
            name="ck_daily_lifetime_non_negative",
        ),
        CheckConstraint(
            "focus_seconds >= 0",
            name="ck_daily_focus_non_negative",
        ),
        CheckConstraint(
            "focus_seconds <= lifetime_seconds",
            name="ck_daily_focus_lte_lifetime",
        ),
        Index("idx_app_daily_usage_synced", "synced"),
    )

    def __repr__(self):
        return (
            f"<AppDailyUsage("
            f"application_id={self.application_id}, "
            f"date={self.date}, "
            f"lifetime={self.lifetime_seconds}s, "
            f"focus={self.focus_seconds}s"
            f")>"
        )


class ProcessSession(Base):
    __tablename__ = "process_sessions"

    id = Column(Integer, primary_key=True)

    summary_id = Column(
        Integer,
        ForeignKey("app_usage_summary.id"),
        nullable=False,
        index=True,
    )

    process_name = Column(String, nullable=False)

    session_start_time = Column(DateTime, nullable=False, index=True)
    session_end_time = Column(DateTime, nullable=True)

    total_lifetime_seconds = Column(BigInteger, nullable=False, default=0)
    total_focus_seconds = Column(BigInteger, nullable=False, default=0)

    synced = Column(Boolean, nullable=False, default=False)

    summary = relationship(
        "AppUsageSummary",
        back_populates="sessions",
    )

    activities = relationship(
        "FocusActivity",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "total_lifetime_seconds >= 0",
            name="ck_session_lifetime_non_negative",
        ),
        CheckConstraint(
            "total_focus_seconds >= 0",
            name="ck_session_focus_non_negative",
        ),
        CheckConstraint(
            "total_focus_seconds <= total_lifetime_seconds",
            name="ck_session_focus_lte_lifetime",
        ),
        CheckConstraint(
            "session_end_time IS NULL OR session_end_time >= session_start_time",
            name="ck_session_end_after_start",
        ),
        Index("idx_process_sessions_synced", "synced"),
    )

    def __repr__(self):
        return (
            f"<ProcessSession("
            f"summary_id={self.summary_id}, "
            f"process_name='{self.process_name}', "
            f"start='{self.session_start_time}', "
            f"end='{self.session_end_time}', "
            f"lifetime={self.total_lifetime_seconds}s, "
            f"focus={self.total_focus_seconds}s"
            f")>"
        )


class FocusActivity(Base):
    __tablename__ = "focus_activities"

    id = Column(Integer, primary_key=True)

    session_id = Column(
        Integer,
        ForeignKey("process_sessions.id"),
        nullable=False,
        index=True,
    )

    window_title = Column(String, nullable=False)

    focus_start_time = Column(DateTime, nullable=True, index=True)
    focus_end_time = Column(DateTime, nullable=True)

    focus_duration_seconds = Column(BigInteger, nullable=False, default=0)

    synced = Column(Boolean, nullable=False, default=False)

    session = relationship(
        "ProcessSession",
        back_populates="activities",
    )

    __table_args__ = (
        CheckConstraint(
            "focus_duration_seconds >= 0",
            name="ck_focus_duration_non_negative",
        ),
        CheckConstraint(
            "focus_start_time IS NULL OR focus_end_time IS NULL OR focus_end_time >= focus_start_time",
            name="ck_focus_end_after_start",
        ),
        Index("idx_focus_activities_synced", "synced"),
    )

    def __repr__(self):
        return (
            f"<FocusActivity("
            f"session_id={self.session_id}, "
            f"title='{self.window_title}', "
            f"start='{self.focus_start_time}', "
            f"end='{self.focus_end_time}', "
            f"duration={self.focus_duration_seconds}s"
            f")>"
        )


class AppGroup(Base):
    __tablename__ = "app_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)

    applications = relationship(
        "WatchedApplication",
        secondary="app_group_associations",
        back_populates="groups",
    )

    def __repr__(self):
        return f"<AppGroup(id={self.id}, name='{self.name}')>"


class AppGroupAssociation(Base):
    __tablename__ = "app_group_associations"

    application_id = Column(
        Integer,
        ForeignKey("watched_applications.id"),
        primary_key=True,
    )
    group_id = Column(
        Integer,
        ForeignKey("app_groups.id"),
        primary_key=True,
    )


class AppColorTag(Base):
    __tablename__ = "app_color_tags"

    application_id = Column(
        Integer,
        ForeignKey("watched_applications.id"),
        primary_key=True,
    )
    color = Column(String, nullable=False)

    application = relationship(
        "WatchedApplication",
        back_populates="color_tags",
    )

    def __repr__(self):
        return f"<AppColorTag(app_id={self.application_id}, color='{self.color}')>"
