"""request_sync_now(): 通过 queued signal 触发后台 worker 的 perform_sync_check。

不联网、不查库：用假的 worker 替换真实 worker，仅验证信号接线与线程投递。
"""
import _common  # noqa: F401

import sys

from PySide6.QtCore import QObject, Signal, Slot, QElapsedTimer, QThread
from PySide6.QtWidgets import QApplication

import core.sync_controller as sc

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


class FakeWorker(QObject):
    status_updated = Signal(str)
    finished = Signal()

    def __init__(self, token_provider, interval_seconds=60):
        super().__init__()
        self.calls = []

    @Slot()
    def start_service(self):
        self.calls.append("start_service")

    @Slot()
    def perform_sync_check(self):
        self.calls.append("perform_sync_check")

    @Slot()
    def stop(self):
        self.finished.emit()

    @Slot()
    def pause(self):
        self.calls.append("pause")

    @Slot()
    def resume(self):
        self.calls.append("resume")

    @Slot(int)
    def set_interval(self, seconds):
        self.calls.append("set_interval")


# 用假 worker 替换真实 worker（不联网、不查库）
sc.ApiSyncWorker = FakeWorker


def wait_until(pred, timeout_ms=3000):
    t = QElapsedTimer()
    t.start()
    while not pred() and t.elapsed() < timeout_ms:
        app.processEvents()
        QThread.msleep(10)
    return pred()


ctrl = sc.SyncController(token_provider=lambda: None)
ctrl.start()

check("worker 已创建", ctrl._worker is not None)
check("worker 已收到启动", wait_until(lambda: "start_service" in ctrl._worker.calls))

ctrl.request_sync_now()
check("request_sync_now 触发 perform_sync_check",
      wait_until(lambda: "perform_sync_check" in ctrl._worker.calls))

before = ctrl._worker.calls.count("perform_sync_check")
ctrl.request_sync_now()
check("可重复请求触发",
      wait_until(lambda: ctrl._worker.calls.count("perform_sync_check") > before))

ctrl.stop(timeout_ms=2000)
check("线程已停止", wait_until(lambda: ctrl._thread is None or not ctrl._thread.isRunning()))

app.processEvents()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
