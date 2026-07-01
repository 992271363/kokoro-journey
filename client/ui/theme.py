import winreg
from PySide6.QtWidgets import QApplication
from ui.styles import MODERN_LIGHT_QSS, MODERN_DARK_QSS
from util.config import Settings


def get_system_theme() -> str:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0,
            winreg.KEY_READ,
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        return "light"


def apply_theme(mode: str):
    resolved = mode
    if mode == "system":
        resolved = get_system_theme()

    if resolved == "dark":
        QApplication.instance().setStyleSheet(MODERN_DARK_QSS)
    else:
        QApplication.instance().setStyleSheet(MODERN_LIGHT_QSS)

    Settings().set("themeMode", mode)
