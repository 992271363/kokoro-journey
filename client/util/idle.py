import ctypes


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


def get_system_idle_seconds() -> float:
    """
    返回系统空闲秒数（距最后一次键盘/鼠标输入）。

    基于 Windows API GetLastInputInfo 实现，检测的是全系统的
    键鼠输入，可用于判断用户是否暂离电脑。调用失败时返回 0.0。
    """
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    now = ctypes.windll.kernel32.GetTickCount()
    return max(0.0, (now - lii.dwTime) / 1000.0)
