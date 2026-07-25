from pydantic import BaseModel
from datetime import datetime, date
from typing import List, Optional

# 客户端发来的每个焦点活动的数据
class SyncFocusActivity(BaseModel):
    window_title: str
    focus_start_time: Optional[datetime] = None
    focus_end_time: Optional[datetime] = None
    focus_duration_seconds: int

# 客户端发来的每个会话的数据包
class SyncProcessSession(BaseModel):
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
class SyncAppDailyUsage(BaseModel):
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
