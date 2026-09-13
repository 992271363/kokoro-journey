"""测试公共初始化：离屏渲染、隔离用户目录、把 client 加入 sys.path。

所有 test_*.py 顶部先 `import _common`，再做各自的 import。
"""
import atexit
import gc
import os
import shutil
import sys
import tempfile
import time

_TMP_DIRS = []


def tmpdir(prefix="kokoro_tests_"):
    """创建隔离临时目录并登记，测试进程退出时自动删除。"""
    path = tempfile.mkdtemp(prefix=prefix)
    _TMP_DIRS.append(path)
    return path


@atexit.register
def _cleanup_tmp_dirs():
    # 先释放已打开的 SQLite 连接，否则 Windows 下 local_client.db 被占用删不掉。
    # 只用已导入的模块，避免在退出时反向触发数据库初始化。
    database = sys.modules.get("db.database")
    if database is not None:
        try:
            database.engine.dispose()
        except Exception:
            pass
    gc.collect()

    for path in _TMP_DIRS:
        for _ in range(3):
            try:
                shutil.rmtree(path)
                break
            except OSError:
                time.sleep(0.1)


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 保留真实用户目录（迁移测试需要复制它作为“旧数据”样本）
REAL_LOCALAPPDATA = os.environ.get("LOCALAPPDATA")
# 隔离：测试绝不读写真实用户数据/设置
os.environ["LOCALAPPDATA"] = tmpdir("kokoro_tests_")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT = os.path.join(_REPO, "client")
if _CLIENT not in sys.path:
    sys.path.insert(0, _CLIENT)


def patch_heavy(window_cls):
    """避免真实启动监控/同步线程与托盘。"""
    from core.controller import MonitorController
    from core.sync_controller import SyncController

    MonitorController.start = lambda self, apps=None: None
    SyncController.start = lambda self: None
    window_cls._retry_failed_sessions = lambda self: None

    def fake_tray(self):
        self._tray_icon = _FakeTray()

    window_cls._setup_tray_icon = fake_tray


class _FakeTray:
    """最小托盘替身：只覆盖代码里用到的接口。"""

    def show(self):
        pass

    def hide(self):
        pass

    def isVisible(self):
        return False

    def setIcon(self, *a, **k):
        pass

    def showMessage(self, *a, **k):
        pass



def ensure_db():
    from db.database import create_db_and_tables

    create_db_and_tables()
