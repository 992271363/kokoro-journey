from PySide6.QtCore import QObject, Signal, QThread, Qt
from core.sync import ApiSyncWorker
from util.shutdown import wait_for_thread
from util.config import Settings
from typing import Callable, Optional


class SyncController(QObject):
    status_updated = Signal(str)
    _request_stop = Signal()
    _request_pause = Signal()
    _request_resume = Signal()
    _request_set_interval = Signal(int)

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
        self._request_pause.connect(self._worker.pause, Qt.QueuedConnection)
        self._request_resume.connect(self._worker.resume, Qt.QueuedConnection)
        self._request_set_interval.connect(self._worker.set_interval, Qt.QueuedConnection)
        self._worker.status_updated.connect(self.status_updated, Qt.QueuedConnection)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        if not Settings().get("syncEnabled", True):
            self.pause()

    def stop(self, timeout_ms=3000, dialog=None, status_text=""):
        if self._worker and self._thread and self._thread.isRunning():
            print("[SyncController] 正在停止同步线程...")
            self._request_stop.emit()
            wait_for_thread(self._thread, timeout_ms, dialog, status_text)
            print("[SyncController] 同步线程已停止")

    def pause(self):
        if self._worker:
            self._request_pause.emit()

    def resume(self):
        if self._worker:
            self._request_resume.emit()

    def set_interval(self, seconds: int):
        if self._worker:
            self._request_set_interval.emit(int(seconds))

    def _on_thread_finished(self):
        if self._worker:
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.deleteLater()
            self._thread = None
