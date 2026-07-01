import os


def normalize_exe_path(path: str) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path.strip()))


import sys
import json


def _program_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _settings_dir() -> str:
    """settings.json 的固定位置（始终在 AppData，不随程序位置变化）。"""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        local_appdata = os.path.expanduser("~\\AppData\\Local")
    return os.path.join(local_appdata, "desktopActivitySystem")


def _from_cmdline() -> str | None:
    for arg in sys.argv[1:]:
        if arg.startswith("--data-dir="):
            return arg.split("=", 1)[1].strip().strip('"')
    return None


def _from_portable() -> str | None:
    if os.path.exists(os.path.join(_program_dir(), "portable.txt")):
        return os.path.join(_program_dir(), "data")
    return None


def _from_settings_json() -> str | None:
    path = os.path.join(_settings_dir(), "settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            d = data.get("dataDirectory")
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
    return None


def _default_appdata() -> str:
    return os.path.join(_settings_dir(), "data")


def get_data_dir() -> str:
    for fn in (_from_cmdline, _from_portable, _from_settings_json, _default_appdata):
        d = fn()
        if d:
            return d
    return _default_appdata()


def is_data_dir_configured() -> bool:
    d = _from_settings_json() or _from_portable()
    if d is None:
        return False
    if not os.path.exists(os.path.join(d, "local_client.db")):
        return False
    return True
