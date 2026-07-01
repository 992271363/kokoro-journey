
from PySide6.QtCore import QObject, Signal, Slot, QTimer, Qt
from sqlalchemy.orm import joinedload, Session
from db.database import SessionLocal
from db.models import FocusActivity, ProcessSession, AppUsageSummary
from core.api import send_data_to_api
from typing import List

def get_and_prepare_sync_data():
    db = SessionLocal()
    try:
        activities_to_sync = db.query(FocusActivity).options(
            joinedload(FocusActivity.session).joinedload(ProcessSession.summary).joinedload(AppUsageSummary.application)
        ).filter(FocusActivity.synced == False).all()
        if not activities_to_sync:
            return [], []
        sessions_map = {}
        for activity in activities_to_sync:
            session_id = activity.session_id
            if session_id not in sessions_map:
                sessions_map[session_id] = {
                    "process_name": activity.session.process_name,
                    "executable_path": activity.session.summary.application.executable_path,
                    "session_start_time": activity.session.session_start_time.isoformat(),
                    "session_end_time": activity.session.session_end_time.isoformat(),
                    "total_lifetime_seconds": activity.session.total_lifetime_seconds,
                    "total_focus_seconds": activity.session.total_focus_seconds,
                    "activities": []
                }

            sessions_map[session_id]["activities"].append({
                "window_title": activity.window_title,
                "focus_duration_seconds": activity.focus_duration_seconds
            })

        data_to_send = list(sessions_map.values())
        print(f"[Sync Util] 发现 {len(data_to_send)} 个会话包含未同步数据，准备上传...")
        return data_to_send, activities_to_sync
    finally:
        db.close()

def mark_activities_as_synced(activities: List[FocusActivity]):
    if not activities:
        return
    db = SessionLocal()
    try:
        activity_ids = [activity.id for activity in activities]
        db.query(FocusActivity).filter(FocusActivity.id.in_(activity_ids)).update({"synced": True})
        db.commit()
        print(f"[Sync Util] 已将 {len(activity_ids)} 条焦点活动记录标记为已同步。")
    except Exception as e:
        print(f"[Sync Util] 标记同步状态时出错: {e}")
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

    @Slot()  # 确保这是个槽（在目标线程执行）
    def start_service(self):
        """在 worker 线程中被调用，创建并启动 QTimer（QTimer 必须在这里创建）"""
        print(f"[Sync Service] QTimer 服务已在后台线程启动，每 {self.interval // 1000} 秒检查一次。")
        self._running = True
        # 不要把 parent 设为主线程对象，用 None 或 self（self 已在目标线程）
        self._timer = QTimer()
        self._timer.setInterval(self.interval)
        self._timer.timeout.connect(self.perform_sync_check)
        self._timer.start()
        # 立即触发一次检查（可选）
        self.perform_sync_check()

    @Slot()
    def perform_sync_check(self):
        # 早退条件：如果已经停止则不执行
        if not self._running:
            return
        print("\n--- [Sync Service] QTimer 触发新一轮后台同步检查 ---")
        token = self._token_provider() if self._token_provider else None
        if not token:
            self.status_updated.emit("未登录，跳过后台同步。")
            return

        data_to_send, activities_to_mark = get_and_prepare_sync_data()
        if not data_to_send:
            self.status_updated.emit("后台检查：数据已是最新。")
        else:
            self.status_updated.emit(f"后台发现 {len(data_to_send)} 个新会话，上传中...")
            success = send_data_to_api(data_to_send, endpoint="/sync/sessions/", token=token)
            if success:
                mark_activities_as_synced(activities_to_mark)
                self.status_updated.emit(f"后台成功同步 {len(data_to_send)} 个会话。")
            else:
                self.status_updated.emit("后台同步失败，将在下一周期重试。")

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

from PySide6.QtCore import QObject, Signal, QThread, Qt
from core.sync import ApiSyncWorker, get_and_prepare_sync_data, mark_activities_as_synced
from util.shutdown import wait_for_thread
from typing import Callable, Optional


class SyncController(QObject):
    status_updated = Signal(str)
    _request_stop = Signal()

    def __init__(self, token_provider: Callable[[], Optional[str]], parent=None):
        super().__init__(parent)
        self._token_provider = token_provider
        self._thread = None
        self._worker = None

    def start(self):
        if self._thread and self._thread.isRunning():
            return
        self._thread = QThread(self)
        self._worker = ApiSyncWorker(self._token_provider)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start_service)
        self._request_stop.connect(self._worker.stop, Qt.QueuedConnection)
        self._worker.status_updated.connect(self.status_updated, Qt.QueuedConnection)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def stop(self, timeout_ms=3000, dialog=None, status_text=""):
        if self._worker and self._thread and self._thread.isRunning():
            print("[SyncController] 正在停止同步线程...")
            self._request_stop.emit()
            wait_for_thread(self._thread, timeout_ms, dialog, status_text)
            print("[SyncController] 同步线程已停止")

    def _on_thread_finished(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
