import os
import json
import psutil
import datetime
import time
import win32gui
import win32process
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from typing import List, Dict, TypedDict
from util.path import normalize_exe_path
from util.path import get_data_dir

# --- 失败队列文件路径 ---
_FAILED_QUEUE_DIR = get_data_dir()
os.makedirs(_FAILED_QUEUE_DIR, exist_ok=True)
_FAILED_QUEUE_PATH = os.path.join(_FAILED_QUEUE_DIR, "failed_sessions.json")
_DEAD_QUEUE_PATH = os.path.join(_FAILED_QUEUE_DIR, "failed_sessions_dead.json")
_MAX_RETRIES = 10


def _load_failed_queue() -> List[dict]:
    if not os.path.exists(_FAILED_QUEUE_PATH):
        return []
    try:
        with open(_FAILED_QUEUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_failed_queue(queue: List[dict]) -> None:
    try:
        with open(_FAILED_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"[Failed Queue] 写入队列文件失败: {e}")


def _load_dead_queue() -> List[dict]:
    if not os.path.exists(_DEAD_QUEUE_PATH):
        return []
    try:
        with open(_DEAD_QUEUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_dead_queue(queue: List[dict]) -> None:
    try:
        with open(_DEAD_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"[Failed Queue] 写入死信文件失败: {e}")


def _archive_to_dead_letter(item: dict) -> None:
    dead = _load_dead_queue()
    dead.append(item)
    _save_dead_queue(dead)
    print(f"[Failed Queue] 会话已归档到冷存储，当前死信数量: {len(dead)}")


def _enqueue_failed_session(
    exe_path: str,
    exe_name: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    focus_details: dict,
    error: str,
) -> None:
    queue = _load_failed_queue()
    queue.append({
        "executable_path": exe_path,
        "executable_name": exe_name,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "focus_details": focus_details,
        "retry_count": 0,
        "last_error": str(error),
        "failed_at": datetime.datetime.now().isoformat(),
    })
    _save_failed_queue(queue)
    print(f"[Failed Queue] 会话已入队，当前队列长度: {len(queue)}")


def retry_failed_sessions() -> tuple[int, int]:
    """
    在主线程中调用，重试队列中的失败会话。
    返回 (成功数, 剩余数)。
    """
    from db.database import SessionLocal
    from core.tracker import record_process_session

    queue = _load_failed_queue()
    if not queue:
        return 0, 0

    success_count = 0
    remaining = []

    for item in queue:
        if item.get("retry_count", 0) >= _MAX_RETRIES:
            print(f"[Failed Queue] 会话达到最大重试次数，归档到冷存储: {item['executable_name']}")
            _archive_to_dead_letter(item)
            continue

        item["retry_count"] = item.get("retry_count", 0) + 1

        db = SessionLocal()
        try:
            record_process_session(
                db=db,
                executable_path=item["executable_path"],
                executable_name=item["executable_name"],
                start_time=datetime.datetime.fromisoformat(item["start_time"]),
                end_time=datetime.datetime.fromisoformat(item["end_time"]),
                focus_details=item["focus_details"],
            )
            success_count += 1
            print(f"[Failed Queue] 重试成功: {item['executable_name']}")
        except Exception as e:
            db.rollback()
            item["last_error"] = str(e)
            item["failed_at"] = datetime.datetime.now().isoformat()
            remaining.append(item)
            print(f"[Failed Queue] 重试失败 ({item['retry_count']}/{_MAX_RETRIES}): {item['executable_name']} - {e}")
        finally:
            db.close()

    _save_failed_queue(remaining)
    return success_count, len(remaining)


def get_failed_queue_count() -> int:
    return len(_load_failed_queue())


def restore_dead_letter_sessions() -> int:
    """
    程序启动时调用：把冷存储的死信捞回主队列重新重试。
    死信的 retry_count 会被重置为 0，然后清空冷存储文件。
    返回捞回的会话数量。
    """
    dead = _load_dead_queue()
    if not dead:
        return 0
    main_queue = _load_failed_queue()
    for item in dead:
        item["retry_count"] = 0
        main_queue.append(item)
    _save_failed_queue(main_queue)
    _save_dead_queue([])
    print(f"[Failed Queue] 已从冷存储捞回 {len(dead)} 条死信会话到主队列")
    return len(dead)


# --- 基础类型 ---
class ProcessInfo(TypedDict):
    pid: int
    name: str
    exe: str

# --- 获取进程列表 (保留原逻辑) ---
def get_process_list() -> List[ProcessInfo]:
    attrs = ['pid', 'name', 'exe']
    process_data: List[ProcessInfo] = []
    path_separator = os.sep
    for proc in psutil.process_iter(attrs=attrs):
        try:
            proc_info = {
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'exe': proc.info['exe'] or 'N/A'
            }
            if not proc_info['exe'] or path_separator not in proc_info['exe'] or proc_info['pid'] in [0, 4]:
                continue
            process_data.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return process_data

# --- 全局监控 Worker ---
class ActiveSession:
    def __init__(self, exe_name, exe_path, start_time):
        self.exe_name = exe_name
        self.exe_path = exe_path
        self.start_time = start_time
        self.focus_seconds = 0.0
        self.focus_details = {}
        self.is_focused = False

class GlobalMonitorWorker(QObject):
    status_updated = Signal(dict)
    session_finished = Signal(str, int)
    session_save_failed = Signal(str, str)
    finished = Signal()

    def __init__(self, watched_apps_info: List[tuple]):
        """
        watched_apps_info: List[(exe_path, exe_name), ...]
        """
        super().__init__()
        self._target_apps = {
            normalize_exe_path(path): (normalize_exe_path(path), name)
            for path, name in watched_apps_info
        }
        self._running = True
        self._paused = False
        self._mutex = QMutex()
        self._active_sessions: Dict[str, ActiveSession] = {}
        self._pid_to_path: Dict[int, str] = {}

    def update_watch_list(self, new_list: List[tuple]):
        """
        new_list: List[(exe_path, exe_name), ...]
        """
        with QMutexLocker(self._mutex):
            self._target_apps = {
                normalize_exe_path(path): (normalize_exe_path(path), name)
                for path, name in new_list
            }

    def force_stop_tracking(self, exe_path: str):
        path_key = normalize_exe_path(exe_path)
        with QMutexLocker(self._mutex):
            self._target_apps.pop(path_key, None)
            self._active_sessions.pop(path_key, None)
            stale_pids = [pid for pid, p in self._pid_to_path.items() if p == path_key]
            for pid in stale_pids:
                del self._pid_to_path[pid]

    def stop(self):
        self._running = False

    def pause(self):
        with QMutexLocker(self._mutex):
            self._paused = True
            sessions = list(self._active_sessions.values())
            self._active_sessions.clear()
            self._pid_to_path.clear()
        for session in sessions:
            self._save_session(session)

    def resume(self):
        with QMutexLocker(self._mutex):
            self._paused = False

    @property
    def is_paused(self):
        return self._paused

    def run(self):
        print("[Global Monitor] 服务启动...")
        while self._running:
            try:
                if not self._paused:
                    self._check_processes_lifecycle_nonblocking()
                    self._check_focus_nonblocking(1.0)
                self._emit_status()

                # 灵敏等待，每 0.1 秒检查一次是否停止，总共 1 秒
                for _ in range(10):
                    if not self._running:
                        break
                    time.sleep(0.1)

            except Exception as e:
                print(f"[Global Monitor] 异常: {e}")
                time.sleep(0.1)

        self._force_close_all()
        self.finished.emit()

    def _check_processes_lifecycle_nonblocking(self):
        # 锁外：遍历进程（耗时），仅收集存活进程的 (pid, exe)
        proc_list = []
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            if not self._running:
                break
            try:
                if not proc.info['exe']:
                    continue
                proc_list.append((proc.info['pid'], proc.info['exe']))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        sessions_to_save = []
        with QMutexLocker(self._mutex):
            alive_paths = set()
            for p_pid, p_path in proc_list:
                p_path_key = normalize_exe_path(p_path)
                if p_path_key in self._target_apps:
                    matched_path, matched_name = self._target_apps[p_path_key]
                    alive_paths.add(p_path_key)
                    self._pid_to_path[p_pid] = p_path_key
                    if p_path_key not in self._active_sessions:
                        self._active_sessions[p_path_key] = ActiveSession(matched_name, matched_path, datetime.datetime.now())
            for path in list(self._active_sessions.keys()):
                if path not in alive_paths:
                    sessions_to_save.append(self._active_sessions[path])
                    del self._active_sessions[path]

        # 锁外：数据库写入（耗时）
        for session in sessions_to_save:
            self._save_session(session)

    def _check_focus_nonblocking(self, delta_seconds: float):
        if not self._running:
            return
        try:
            # 锁外：获取前台窗口信息（win32 调用）
            fg_window = win32gui.GetForegroundWindow()
            fg_pid = None
            window_title = "未知窗口"
            if fg_window:
                _, fg_pid = win32process.GetWindowThreadProcessId(fg_window)
                window_title = win32gui.GetWindowText(fg_window) or "未知窗口"
            # 锁内：更新共享会话状态
            with QMutexLocker(self._mutex):
                for session in self._active_sessions.values():
                    session.is_focused = False
                if fg_pid is not None:
                    path = self._pid_to_path.get(fg_pid)
                    if path and path in self._active_sessions:
                        session = self._active_sessions[path]
                        session.is_focused = True
                        session.focus_seconds += delta_seconds
                        session.focus_details[window_title] = session.focus_details.get(window_title, 0.0) + delta_seconds
        except Exception:
            pass

    def _save_session(self, session: ActiveSession):
        from db.database import SessionLocal
        from core.tracker import record_process_session
        end_time = datetime.datetime.now()
        if (end_time - session.start_time).total_seconds() < 2: return
        db = SessionLocal()
        try:
            record_process_session(db=db,
                                   executable_path=session.exe_path,
                                   executable_name=session.exe_name,
                                   start_time=session.start_time,
                                   end_time=end_time,
                                   focus_details=session.focus_details)
            self.session_finished.emit(session.exe_name, int((end_time - session.start_time).total_seconds()))
        except Exception as e:
            # 不再静默吞掉：写入文件队列，并通知 UI
            db.rollback()
            _enqueue_failed_session(
                session.exe_path,
                session.exe_name,
                session.start_time,
                end_time,
                session.focus_details,
                str(e),
            )
            self.session_save_failed.emit(session.exe_name, str(e))
            print(f"[DB Save Error] {e} — 已入队稍后重试")
        finally:
            db.close()

    def _force_close_all(self):
        with QMutexLocker(self._mutex):
            sessions = list(self._active_sessions.values())
            self._active_sessions.clear()
            self._pid_to_path.clear()
        for session in sessions:
            self._save_session(session)

    def _emit_status(self):
        status_data = {}
        now = datetime.datetime.now()
        with QMutexLocker(self._mutex):
            for path, session in self._active_sessions.items():
                runtime = int((now - session.start_time).total_seconds())
                status_data[path] = {
                    "name": session.exe_name,
                    "pid": 0,
                    "focus": int(session.focus_seconds),
                    "runtime_seconds": runtime,
                    "start_str": session.start_time.strftime("%H:%M:%S"),
                    "is_focused": session.is_focused,
                }
        self.status_updated.emit(status_data)
