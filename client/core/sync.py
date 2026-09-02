import datetime

from PySide6.QtCore import QObject, Signal, Slot, QTimer, Qt
from sqlalchemy.orm import joinedload, Session
from db.database import SessionLocal
from db.models import ProcessSession, AppUsageSummary, AppDailyUsage
from core.api import send_data_to_api
from typing import List


def _to_utc_iso(dt):
    """把 naive 本地时间转为 UTC 的 ISO 字符串；None 原样返回。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(datetime.timezone.utc).isoformat()

def get_and_prepare_sync_data():
    db = SessionLocal()
    try:
        sessions_to_sync = db.query(ProcessSession).options(
            joinedload(ProcessSession.activities),
            joinedload(ProcessSession.summary).joinedload(AppUsageSummary.application)
        ).filter(ProcessSession.synced == False).all()

        if not sessions_to_sync:
            return [], []

        data_to_send = []
        for session in sessions_to_sync:
            app = session.summary.application
            activities_data = []
            for activity in session.activities:
                activities_data.append({
                    "windowTitle": activity.window_title,
                    "focusStartTime": _to_utc_iso(activity.focus_start_time),
                    "focusEndTime": _to_utc_iso(activity.focus_end_time),
                    "focusDurationSeconds": activity.focus_duration_seconds
                })
            data_to_send.append({
                "uid": app.uid,
                "executableName": app.executable_name,
                "executablePath": app.executable_path,
                "launchPath": app.launch_path,
                "isWatched": app.is_watched,
                "isProcessPathDifferent": app.is_process_path_different,
                "isPathExist": app.is_path_exist,
                "processName": session.process_name,
                "sessionStartTime": _to_utc_iso(session.session_start_time),
                "sessionEndTime": _to_utc_iso(session.session_end_time),
                "totalLifetimeSeconds": session.total_lifetime_seconds,
                "totalFocusSeconds": session.total_focus_seconds,
                "activities": activities_data
            })

        print(f"[Sync Util] 发现 {len(data_to_send)} 个会话包含未同步数据，准备上传...")
        return data_to_send, sessions_to_sync
    finally:
        db.close()

def mark_sessions_as_synced(sessions: List[ProcessSession]):
    if not sessions:
        return
    db = SessionLocal()
    try:
        session_ids = [s.id for s in sessions]
        db.query(ProcessSession).filter(ProcessSession.id.in_(session_ids)).update({"synced": True})
        db.commit()
        print(f"[Sync Util] 已将 {len(session_ids)} 个会话标记为已同步。")
    except Exception as e:
        print(f"[Sync Util] 标记同步状态时出错: {e}")
        db.rollback()
    finally:
        db.close()


def get_and_prepare_daily_data():
    db = SessionLocal()
    try:
        daily_to_sync = db.query(AppDailyUsage).options(
            joinedload(AppDailyUsage.application)
        ).filter(AppDailyUsage.synced == False).all()

        if not daily_to_sync:
            return [], []

        data_to_send = []
        for d in daily_to_sync:
            data_to_send.append({
                "uid": d.application.uid,
                "date": d.date.isoformat(),
                "lifetimeSeconds": d.lifetime_seconds,
                "focusSeconds": d.focus_seconds
            })

        print(f"[Sync Util] 发现 {len(data_to_send)} 条每日统计待同步，准备上传...")
        return data_to_send, daily_to_sync
    finally:
        db.close()


def mark_daily_as_synced(daily_list: List[AppDailyUsage]):
    if not daily_list:
        return
    db = SessionLocal()
    try:
        daily_ids = [d.id for d in daily_list]
        db.query(AppDailyUsage).filter(AppDailyUsage.id.in_(daily_ids)).update({"synced": True})
        db.commit()
        print(f"[Sync Util] 已将 {len(daily_ids)} 条每日统计标记为已同步。")
    except Exception as e:
        print(f"[Sync Util] 标记每日同步状态时出错: {e}")
        db.rollback()
    finally:
        db.close()


class ApiSyncWorker(QObject):
    finished = Signal()
    status_updated = Signal(str)

    def __init__(self, token_provider, interval_seconds: int = 60):
        super().__init__()
        self._token_provider = token_provider
        self.interval = interval_seconds * 1000
        self._timer = None
        self._running = False
        self._paused = False

    @Slot()
    def pause(self):
        if self._timer and self._timer.isActive():
            self._timer.stop()
            self._paused = True
            print("[Sync Service] 后台同步已暂停。")
        elif not self._timer and self._running:
            self._paused = True

    @Slot()
    def resume(self):
        self._paused = False
        if self._timer and not self._timer.isActive():
            self._timer.start()
            print(f"[Sync Service] 后台同步已恢复，每 {self.interval // 1000} 秒检查一次。")

    @Slot(int)
    def set_interval(self, seconds: int):
        self.interval = seconds * 1000
        if self._timer:
            self._timer.setInterval(self.interval)

    @Slot()
    def start_service(self):
        """在 worker 线程中被调用，创建并启动 QTimer（QTimer 必须在这里创建）"""
        print(f"[Sync Service] QTimer 服务已在后台线程启动，每 {self.interval // 1000} 秒检查一次。")
        self._running = True
        self._paused = False
        self._timer = QTimer()
        self._timer.setInterval(self.interval)
        self._timer.timeout.connect(self.perform_sync_check)
        self._timer.start()
        # 立即触发一次检查（可选）
        self.perform_sync_check()

    @Slot()
    def perform_sync_check(self):
        # 早退条件：如果已停止或已暂停则不执行
        if not self._running or self._paused:
            return
        print("\n--- [Sync Service] QTimer 触发新一轮后台同步检查 ---")
        token = self._token_provider() if self._token_provider else None
        if not token:
            self.status_updated.emit("未登录，跳过后台同步。")
            return

        data_to_send, sessions_to_mark = get_and_prepare_sync_data()
        if not data_to_send:
            self.status_updated.emit("后台检查：数据已是最新。")
        else:
            self.status_updated.emit(f"后台发现 {len(data_to_send)} 个新会话，上传中...")
            success = send_data_to_api(data_to_send, endpoint="/sync/sessions/", token=token)
            if success:
                mark_sessions_as_synced(sessions_to_mark)
                self.status_updated.emit(f"后台成功同步 {len(data_to_send)} 个会话。")
            else:
                self.status_updated.emit("后台同步失败，将在下一周期重试。")

        # 每日统计同步（在会话之后，确保应用已在服务端创建）
        daily_data, daily_to_mark = get_and_prepare_daily_data()
        if daily_data:
            self.status_updated.emit(f"后台发现 {len(daily_data)} 条每日统计，上传中...")
            daily_success = send_data_to_api(daily_data, endpoint="/sync/daily/", token=token)
            if daily_success:
                mark_daily_as_synced(daily_to_mark)
                self.status_updated.emit(f"后台成功同步 {len(daily_data)} 条每日统计。")
            else:
                self.status_updated.emit("后台每日统计同步失败，将在下一周期重试。")

    @Slot()  # 这个 stop 必须在 worker 线程中运行（通过 queued connection 调用）
    def stop(self):
        print("[Sync Service] 收到停止信号（slot），准备停止 QTimer ...")
        # 标志位先关
        self._running = False
        # 在本线程安全停止 timer
        if self._timer and self._timer.isActive():
            try:
                self._timer.stop()
                print("[Sync Service] QTimer 已停止。")
            except Exception as e:
                print("[Sync Service] 停止定时器时异常:", e)
        # 清理 timer 对象
        if self._timer:
            # 添加安全延迟，确保定时器完全停止
            QTimer.singleShot(100, self._safe_delete_timer)
        else:
            self.finished.emit()

        # 告诉外界我们已经完成，触发 thread.quit()（由 main 端连接）
    @Slot()
    def _safe_delete_timer(self):
        """确保在定时器完全停止后安全删除"""
        if self._timer:
            self._timer.deleteLater()
            self._timer = None
        self.finished.emit()
