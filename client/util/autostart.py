import sys
import os
import winreg

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "DesktopActivitySystem"


def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def is_available() -> bool:
    return getattr(sys, "frozen", False)


def is_enabled() -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ
        )
        value, _ = winreg.QueryValueEx(key, _APP_NAME)
        winreg.CloseKey(key)
        return os.path.normcase(os.path.normpath(value)) == os.path.normcase(
            os.path.normpath(_exe_path())
        )
    except FileNotFoundError:
        return False
    except Exception:
        return False


def enable() -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _exe_path())
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def disable() -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_WRITE
        )
        winreg.DeleteValue(key, _APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def fix_path() -> bool:
    if not is_enabled():
        return False
    return enable()
