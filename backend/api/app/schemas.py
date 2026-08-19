from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from datetime import datetime, date
from typing import List, Optional

# 所有参与 HTTP 边界传输的模型统一使用 camelCase 别名：
# - 请求体：客户端发送 camelCase，Pydantic 按 alias 解析到字段
# - 响应体：序列化时按 alias 输出 camelCase
# - populate_by_name=True 允许同时按字段名使用（兼容内部直接构造）
class CamelAliasModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# 客户端发来的每个焦点活动的数据
class SyncFocusActivity(CamelAliasModel):
    window_title: str
    focus_start_time: Optional[datetime] = None
    focus_end_time: Optional[datetime] = None
    focus_duration_seconds: int

# 客户端发来的每个会话的数据包
class SyncProcessSession(CamelAliasModel):
    uid: str
    executable_name: str
    executable_path: str
    launch_path: Optional[str] = None
    is_watched: bool = True
    is_process_path_different: bool = False
    is_path_exist: bool = True
    process_name: str
    session_start_time: datetime
    session_end_time: datetime
    total_lifetime_seconds: int
    total_focus_seconds: int
    activities: List[SyncFocusActivity]

# 客户端发来的每日统计数据
class SyncAppDailyUsage(CamelAliasModel):
    uid: str
    date: date
    lifetime_seconds: int
    focus_seconds: int

# 用于 API 输出和内部使用的模型

# 用户相关的模型
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None

class UserCreate(UserBase): 
    password: str

class User(UserBase):
    id: int
    class Config:
        from_attributes = True

# 用于未来仪表盘显示的总账数据模型
class AppUsageSummary(BaseModel):
    id: int
    first_seen_at: Optional[datetime]
    last_seen_start_at: Optional[datetime]
    last_seen_end_at: Optional[datetime]
    total_lifetime_seconds: int
    total_focus_time_seconds: int
    
    class Config:
        from_attributes = True

# ─── Dashboard 响应模型 ───
# 字段名保持 snake_case，序列化时经 alias_generator 输出 camelCase。

class DashboardStats(CamelAliasModel):
    today_focus_seconds: int
    total_apps_tracked: int
    most_used_app_today: Optional[str] = None
    this_week_lifetime_seconds: int


class AppSummaryView(CamelAliasModel):
    last_seen_end_at: Optional[datetime] = None
    total_lifetime_seconds: int
    total_focus_time_seconds: int


class TopAppItem(CamelAliasModel):
    id: int
    executable_name: str
    summary: AppSummaryView


class RecentActivityItem(CamelAliasModel):
    id: int
    process_name: str
    session_start_time: datetime
    session_end_time: Optional[datetime] = None
    total_lifetime_seconds: int
    total_focus_seconds: int