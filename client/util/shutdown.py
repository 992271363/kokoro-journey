import time
from PySide6.QtWidgets import QApplication


def wait_for_thread(thread, timeout_ms, dialog=None, status_text=""):
    start_time = time.time() * 1000
    check_count = 0

    while thread.isRunning():
        check_count += 1
        if dialog and check_count % 25 == 0:
            elapsed = int((time.time() * 1000 - start_time) / 100) / 10
            dialog.set_status(f"{status_text} (已等待{elapsed}秒)...")

        QApplication.processEvents()

        if (time.time() * 1000 - start_time) > timeout_ms:
            print(f"线程停止超时({timeout_ms}ms)，线程仍在运行: {thread.isRunning()}")
            break

        time.sleep(0.02)

    print(f"线程等待结束，总共检查{check_count}次，最终状态: {thread.isRunning()}")
