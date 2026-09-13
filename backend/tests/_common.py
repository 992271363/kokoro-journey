"""后端测试公共清理：登记临时文件/目录，进程退出时自动删除。

所有 backend/tests/test_*.py 顶部 `import _common`，用 tmpdir()/tmpfile() 创建。
"""
import atexit
import gc
import os
import shutil
import sys
import tempfile
import time

_TMP_PATHS = []


def tmpdir(prefix):
    path = tempfile.mkdtemp(prefix=prefix)
    _TMP_PATHS.append(path)
    return path


def tmpfile(prefix, suffix=""):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    _TMP_PATHS.append(path)
    return path


def _dispose_engines():
    """释放已创建的 SQLAlchemy 引擎连接，否则 Windows 下临时 .db 被占用删不掉。"""
    sqlalchemy = sys.modules.get("sqlalchemy")
    engine_cls = getattr(getattr(sqlalchemy, "engine", None), "Engine", None)
    if engine_cls is None:
        return
    for obj in gc.get_objects():
        if isinstance(obj, engine_cls):
            try:
                obj.dispose()
            except Exception:
                pass


@atexit.register
def _cleanup_tmp_paths():
    _dispose_engines()
    gc.collect()
    for path in _TMP_PATHS:
        for _ in range(3):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                break
            except OSError:
                time.sleep(0.1)
