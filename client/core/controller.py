from PySide6.QtCore import QObject, Signal, QThread
from core.monitor import GlobalMonitorWorker, get_failed_queue_count, retry_failed_sessions
from db.repository import AppRepository
from util.shutdown import wait_for_thread
from typing import List


class MonitorController(QObject):
    status_updated = Signal(dict)
    session_finished = Signal(str, int)
    session_save_failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    def start(self, watched_apps_info: List[tuple]):
        if self._thread and self._thread.isRunning():
            return
        self._thread = QThread(self)
        self._worker = GlobalMonitorWorker(watched_apps_info)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._thread.quit)
        self._worker.status_updated.connect(self.status_updated)
        self._worker.session_finished.connect(self.session_finished)
        self._worker.session_save_failed.connect(self.session_save_failed)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def update_watch_list(self, new_list: List[tuple]):
        if self._worker:
            self._worker.update_watch_list(new_list)

    def force_stop_tracking(self, exe_path: str):
        if self._worker:
            self._worker.force_stop_tracking(exe_path)

    def pause(self):
        if self._worker:
            self._worker.pause()

    def resume(self):
        if self._worker:
            self._worker.resume()

    @property
    def is_paused(self):
        return self._worker.is_paused if self._worker else True

    def stop(self, timeout_ms=1500, dialog=None, status_text=""):
        if self._worker and self._thread and self._thread.isRunning():
            print("[MonitorController] 正在停止监控线程...")
            self._worker.stop()
            self._thread.quit()
            wait_for_thread(self._thread, timeout_ms, dialog, status_text)
            print("[MonitorController] 监控线程已停止")

    def _on_thread_finished(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
