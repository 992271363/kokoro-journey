import os
import time
import psutil
import datetime
from PySide6.QtCore import QObject, Signal

def get_process_list():
    attrs = ['pid', 'name', 'exe']
    process_data = []
    path_separator = os.sep
    for proc in psutil.process_iter(attrs=attrs):
        try:
            proc_info = {
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'exe': proc.info['exe'] or 'N/A'
            }
            if not proc_info['exe']:
                continue
            if path_separator not in proc_info['exe']:
                continue
            if proc_info['pid'] in [0, 4]:
                continue
            process_data.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return process_data

class ProcessMonitorWorker(QObject):
    process_terminated = Signal(int, datetime.datetime) 
    error_occurred = Signal(str)
    finished = Signal()
    def __init__(self, pid_to_watch):
        super().__init__()
        self._pid = pid_to_watch
        self._is_running = True
    def run_check(self):
        try:
            if not psutil.pid_exists(self._pid):
                self.error_occurred.emit(f"进程 {self._pid} 在监视开始前就不存在。")
                self.finished.emit()
                return
            proc = psutil.Process(self._pid)
            while self._is_running:
                if not proc.is_running():
                    break
                time.sleep(1)
            
            if self._is_running:
                self.process_terminated.emit(self._pid, datetime.datetime.now())
        except psutil.NoSuchProcess:
             if self._is_running:
                 self.process_terminated.emit(self._pid, datetime.datetime.now())
        except Exception as e:
            self.error_occurred.emit(f"监视 PID {self._pid} 时发生意外错误: {e}")
        finally:
            self.finished.emit()
    def stop(self):
        self._is_running = False