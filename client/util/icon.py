from pathlib import Path
from PySide6.QtGui import QIcon, QPixmap, QImage
import win32gui

_icon_cache: dict[str, QIcon] = {}

def get_exe_icon(exe_path: str) -> QIcon:
    if not exe_path:
        return QIcon()
    cached = _icon_cache.get(exe_path)
    if cached is not None:
        return cached
    if not Path(exe_path).exists():
        _icon_cache[exe_path] = QIcon()
        return QIcon()
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        if small:
            icon = QIcon(QPixmap.fromImage(QImage.fromHICON(small[0])))
            win32gui.DestroyIcon(small[0])
            for h in large:
                win32gui.DestroyIcon(h)
        else:
            icon = QIcon()
    except Exception:
        icon = QIcon()
    _icon_cache[exe_path] = icon
    return icon
