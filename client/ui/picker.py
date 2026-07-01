import os
import time
import tempfile
import traceback
import ctypes
import ctypes.wintypes

import win32gui
import win32con
import win32api
import win32process

from PySide6.QtCore import Qt, Signal, QTimer, QObject
from PySide6.QtGui import QPainter, QPen, QColor, QCursor
from PySide6.QtWidgets import QWidget, QApplication, QPushButton


_DEBUG_ENABLED = False
_DEBUG_LOG = os.path.join(tempfile.gettempdir(), "pick_overlay_debug.log")


def debug_log(msg):
    if not _DEBUG_ENABLED:
        return

    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
            f.flush()
    except Exception:
        pass


debug_log("")
debug_log("=" * 80)
debug_log(f"module loaded, pid={os.getpid()}")
debug_log(f"log file={_DEBUG_LOG}")


def enable_dpi_awareness():
    """
    最好在 QApplication 创建之前调用。
    如果你的 main.py 已经更早创建了 QApplication，
    请把这个函数挪到 main.py 最开头执行。
    """
    try:
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        debug_log("DPI awareness: PER_MONITOR_AWARE_V2")
        return
    except Exception:
        debug_log("DPI awareness: SetProcessDpiAwarenessContext failed")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        debug_log("DPI awareness: SetProcessDpiAwareness(2)")
        return
    except Exception:
        debug_log("DPI awareness: SetProcessDpiAwareness failed")

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        debug_log("DPI awareness: SetProcessDPIAware")
    except Exception:
        debug_log("DPI awareness: SetProcessDPIAware failed")


enable_dpi_awareness()


class PickButton(QPushButton):
    pick_requested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setFocusPolicy(Qt.NoFocus)
        self.setContextMenuPolicy(Qt.NoContextMenu)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setDown(False)
            self.clearFocus()

            try:
                self.releaseMouse()
            except Exception:
                pass

            event.accept()
            self.pick_requested.emit()
            return

        if event.button() == Qt.RightButton:
            event.accept()
            return

        event.accept()

    def mouseReleaseEvent(self, event):
        self.setDown(False)
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()


class PickOverlayPane(QWidget):
    _BG_COLOR = QColor(0, 0, 0, 40)
    _CROSS_COLOR = QColor(255, 255, 255, 180)
    _HIGHLIGHT_COLOR = QColor(59, 130, 246, 200)
    _HIGHLIGHT_FILL = QColor(59, 130, 246, 30)

    def __init__(self, manager, screen):
        super().__init__(None)

        self.manager = manager
        self.screen = screen
        self._paint_count = 0

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setContextMenuPolicy(Qt.NoContextMenu)

        self._apply_screen_geometry()

        try:
            geo = self.screen.geometry()
            debug_log(
                f"PickOverlayPane created: screen={self.screen.name()}, "
                f"geo=({geo.x()},{geo.y()},{geo.width()},{geo.height()}), "
                f"dpr={self.screen.devicePixelRatio()}"
            )
        except Exception:
            debug_log("PickOverlayPane created, screen info failed")

    def _apply_screen_geometry(self):
        self.setGeometry(self.screen.geometry())

    def showEvent(self, event):
        debug_log(f"pane showEvent: screen={self.screen.name()}")

        super().showEvent(event)

        self._apply_screen_geometry()

        self.raise_()
        self.activateWindow()
        self.repaint()

    def closeEvent(self, event):
        debug_log(f"pane closeEvent: screen={self.screen.name()}")
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            debug_log("pane mousePressEvent: right button")
            self.manager.request_cancel_by_right_button()
            event.accept()
            return

        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            debug_log("pane mouseReleaseEvent: right button")
            self.manager.request_cancel_by_right_button()
            event.accept()
            return

        event.accept()

    def contextMenuEvent(self, event):
        debug_log("pane contextMenuEvent")
        self.manager.request_cancel_by_right_button()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            debug_log("pane keyPressEvent: Escape")
            self.manager.cancel()
            return

        event.accept()

    def _monitor_rect_physical(self):
        """
        当前 pane 对应屏幕的物理像素矩形。
        """
        geo = self.screen.geometry()
        center = geo.center()

        ratio = self.screen.devicePixelRatio() or 1.0

        physical_point = (
            int(round(center.x() * ratio)),
            int(round(center.y() * ratio)),
        )

        try:
            monitor = win32api.MonitorFromPoint(
                physical_point,
                win32con.MONITOR_DEFAULTTONEAREST,
            )
            info = win32api.GetMonitorInfo(monitor)
            return info["Monitor"]
        except Exception:
            left = int(round(geo.x() * ratio))
            top = int(round(geo.y() * ratio))
            right = int(round((geo.x() + geo.width()) * ratio))
            bottom = int(round((geo.y() + geo.height()) * ratio))
            return left, top, right, bottom

    def _physical_point_to_local(self, x, y):
        """
        把物理像素坐标转换成当前 pane 内部的 Qt 逻辑坐标。
        """
        ratio = self.screen.devicePixelRatio() or 1.0
        monitor_left, monitor_top, _, _ = self._monitor_rect_physical()

        local_x = int(round((x - monitor_left) / ratio))
        local_y = int(round((y - monitor_top) / ratio))
        return local_x, local_y

    def _physical_rect_to_local(self, rect):
        """
        把物理像素矩形转换成当前 pane 内部的 Qt 逻辑矩形。
        """
        left, top, right, bottom = rect
        ratio = self.screen.devicePixelRatio() or 1.0
        monitor_left, monitor_top, _, _ = self._monitor_rect_physical()

        x = int(round((left - monitor_left) / ratio))
        y = int(round((top - monitor_top) / ratio))
        w = int(round((right - left) / ratio))
        h = int(round((bottom - top) / ratio))
        return x, y, w, h

    @staticmethod
    def _intersect_rect(a, b):
        left = max(a[0], b[0])
        top = max(a[1], b[1])
        right = min(a[2], b[2])
        bottom = min(a[3], b[3])

        if right <= left or bottom <= top:
            return None

        return left, top, right, bottom

    def paintEvent(self, event):
        self._paint_count += 1

        if self._paint_count % 30 == 0:
            debug_log(
                f"paint {self._paint_count}, "
                f"screen={self.screen.name()}, "
                f"target={self.manager.target_hwnd}, "
                f"mouse={self.manager.mouse_pos_physical}"
            )

        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            painter.fillRect(self.rect(), self._BG_COLOR)

            mouse_x, mouse_y = self.manager.mouse_pos_physical
            monitor_rect = self._monitor_rect_physical()
            monitor_left, monitor_top, monitor_right, monitor_bottom = monitor_rect

            local_mouse_x, local_mouse_y = self._physical_point_to_local(
                mouse_x,
                mouse_y,
            )

            painter.setPen(QPen(self._CROSS_COLOR, 1))

            if monitor_left <= mouse_x < monitor_right:
                painter.drawLine(local_mouse_x, 0, local_mouse_x, self.height())

            if monitor_top <= mouse_y < monitor_bottom:
                painter.drawLine(0, local_mouse_y, self.width(), local_mouse_y)

            target_hwnd = self.manager.target_hwnd

            if target_hwnd:
                try:
                    target_rect = self.manager.get_window_frame_rect_physical(
                        target_hwnd
                    )
                    visible_part = self._intersect_rect(target_rect, monitor_rect)

                    if visible_part:
                        x, y, w, h = self._physical_rect_to_local(visible_part)
                        painter.fillRect(x, y, w, h, self._HIGHLIGHT_FILL)
                        painter.setPen(QPen(self._HIGHLIGHT_COLOR, 3))
                        painter.drawRect(x, y, w, h)

                except Exception:
                    debug_log("EXCEPTION drawing target rect:")
                    debug_log(traceback.format_exc())

            painter.end()

        except Exception:
            debug_log("EXCEPTION in paintEvent:")
            debug_log(traceback.format_exc())


class PickOverlay(QObject):
    window_picked = Signal(int)
    cancelled = Signal()

    _VK_LBUTTON = 0x01
    _VK_RBUTTON = 0x02
    _VK_ESCAPE = 0x1B

    def __init__(self, parent=None):
        super().__init__(parent)

        debug_log("PickOverlay __init__")

        self._own_pid = os.getpid()

        self._closed = False
        self._right_cancel_pending = False

        self.target_hwnd = None
        self.mouse_pos_physical = win32api.GetCursorPos()

        self._started_with_left_down = self._is_left_down()
        self._start_pos_qt = QCursor.pos()
        self._drag_mode = False

        self._waiting_for_pick_press = not self._started_with_left_down
        self._pick_press_seen = False

        self._panes = []
        self._tick_count = 0
        self._last_target_log = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        debug_log(
            f"PickOverlay timer started, "
            f"mouse={self.mouse_pos_physical}, "
            f"started_left_down={self._started_with_left_down}"
        )

    def __del__(self):
        debug_log("PickOverlay __del__")

    def show(self):
        debug_log("PickOverlay show begin")

        self._create_panes()
        debug_log(f"panes created: {len(self._panes)}")

        self._tick()
        debug_log("first tick done")

        for pane in self._panes:
            pane.show()
            pane.raise_()
            pane.repaint()

        debug_log("PickOverlay show end")

    def close(self):
        debug_log("PickOverlay close called")
        self._close_panes()

    def _create_panes(self):
        debug_log("_create_panes begin")
        self._close_panes()

        screens = QApplication.screens()
        debug_log(f"QApplication screens: {len(screens)}")

        for screen in screens:
            pane = PickOverlayPane(self, screen)
            self._panes.append(pane)

        debug_log(f"_create_panes end: {len(self._panes)}")

    def _close_panes(self):
        debug_log(f"_close_panes: {len(self._panes)}")

        for pane in self._panes:
            try:
                pane.close()
                pane.deleteLater()
            except Exception:
                debug_log("EXCEPTION in _close_panes:")
                debug_log(traceback.format_exc())

        self._panes = []

    def _is_left_down(self):
        return bool(win32api.GetAsyncKeyState(self._VK_LBUTTON) & 0x8000)

    def _is_right_down(self):
        return bool(win32api.GetAsyncKeyState(self._VK_RBUTTON) & 0x8000)

    def _is_escape_down(self):
        return bool(win32api.GetAsyncKeyState(self._VK_ESCAPE) & 0x8000)

    def _tick(self):
        try:
            self._tick_count += 1

            if self._tick_count % 30 == 0:
                debug_log(
                    f"tick {self._tick_count}, "
                    f"closed={self._closed}, "
                    f"target={self.target_hwnd}, "
                    f"mouse={self.mouse_pos_physical}, "
                    f"panes={len(self._panes)}"
                )

            if self._closed:
                debug_log("tick ignored because closed")
                return

            if self._is_escape_down():
                debug_log("escape down, cancel")
                self.cancel()
                return

            self._refresh_target()
            self._poll_mouse_state()

            for pane in self._panes:
                pane.update()

        except Exception:
            debug_log("EXCEPTION in _tick:")
            debug_log(traceback.format_exc())

    def _refresh_target(self):
        try:
            self.mouse_pos_physical = win32api.GetCursorPos()
            x, y = self.mouse_pos_physical

            hwnd = self._find_window_under_physical_point(x, y)

            if hwnd != self.target_hwnd:
                debug_log(f"target changed: {self.target_hwnd} -> {hwnd}")
                self.target_hwnd = hwnd

        except Exception:
            debug_log("EXCEPTION in _refresh_target:")
            debug_log(traceback.format_exc())

    def _find_window_under_physical_point(self, x, y):
        """
        使用物理像素坐标做命中检测。
        注意：不要在 EnumWindows 回调里 return False。
        pywin32 / 打包后的 exe 里，提前停止 EnumWindows 可能会被包装成异常。
        """
        own_pid = self._own_pid
        pane_hwnds = {int(pane.winId()) for pane in self._panes}
        found = []

        def enum_proc(hwnd, _):
            # 已经找到第一个命中的窗口了，继续返回 True。
            # 这样可以避免 return False 导致 EnumWindows 抛 pywintypes.error。
            if found:
                return True

            if hwnd in pane_hwnds:
                return True

            if not win32gui.IsWindowVisible(hwnd):
                return True

            if self.is_cloaked(hwnd):
                return True

            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid == own_pid:
                    return True
            except Exception:
                return True

            try:
                rect = self.get_window_frame_rect_physical(hwnd)
            except Exception:
                return True

            left, top, right, bottom = rect

            if right <= left or bottom <= top:
                return True

            if left <= x < right and top <= y < bottom:
                found.append(hwnd)
                return True

            return True

        try:
            win32gui.EnumWindows(enum_proc, None)
        except Exception:
            # 理论上改完后这里不该再频繁出现。
            # 如果已经找到 hwnd，就不要因为 EnumWindows 后续异常把 target 清空。
            if found:
                debug_log("EnumWindows raised, but hwnd was already found; ignored")
            else:
                debug_log("EXCEPTION in EnumWindows:")
                debug_log(traceback.format_exc())
                return None

        if not found:
            return None

        hwnd = found[0]

        try:
            root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
        except Exception:
            return hwnd

        if root and root not in pane_hwnds:
            try:
                _, root_pid = win32process.GetWindowThreadProcessId(root)
                if root_pid == own_pid:
                    return None
            except Exception:
                pass

            return root

        return hwnd

    def is_cloaked(self, hwnd):
        try:
            DWMWA_CLOAKED = 14
            cloaked = ctypes.c_int(0)

            result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_CLOAKED,
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked),
            )

            return result == 0 and cloaked.value != 0

        except Exception:
            return False

    def get_window_frame_rect_physical(self, hwnd):
        """
        返回窗口可见边界的物理像素坐标。
        """
        try:
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            rect = ctypes.wintypes.RECT()

            result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )

            if result == 0:
                return rect.left, rect.top, rect.right, rect.bottom

        except Exception:
            pass

        return win32gui.GetWindowRect(hwnd)

    def request_cancel_by_right_button(self):
        if self._closed:
            return

        debug_log("request_cancel_by_right_button")

        self._right_cancel_pending = True
        self.target_hwnd = None

        for pane in self._panes:
            pane.update()

    def _poll_mouse_state(self):
        try:
            right_down = self._is_right_down()

            if right_down:
                self.request_cancel_by_right_button()
                return

            if self._right_cancel_pending:
                debug_log("right cancel pending -> cancel")
                self.cancel()
                return

            left_down = self._is_left_down()

            if self._started_with_left_down:
                moved = (
                    QCursor.pos() - self._start_pos_qt
                ).manhattanLength() >= QApplication.startDragDistance()

                if left_down:
                    if moved:
                        if not self._drag_mode:
                            debug_log("drag mode entered")
                        self._drag_mode = True
                    return

                if self._drag_mode:
                    debug_log("left released after drag -> finish pick")
                    self._finish_pick()
                    return

                debug_log("started left down released without drag")
                self._started_with_left_down = False
                self._waiting_for_pick_press = True
                self._pick_press_seen = False
                return

            if self._waiting_for_pick_press:
                if left_down:
                    debug_log("pick press seen")
                    self._pick_press_seen = True
                    self._waiting_for_pick_press = False
                return

            if self._pick_press_seen and not left_down:
                debug_log("pick press released -> finish pick")
                self._finish_pick()

        except Exception:
            debug_log("EXCEPTION in _poll_mouse_state:")
            debug_log(traceback.format_exc())

    def _finish_pick(self):
        debug_log("finish_pick called")

        if self._closed:
            debug_log("finish_pick ignored because closed")
            return

        self._closed = True
        self._timer.stop()

        hwnd = self.target_hwnd
        debug_log(f"finish_pick hwnd={hwnd}")

        self._close_panes()

        if hwnd:
            self.window_picked.emit(int(hwnd))
            debug_log("window_picked emitted")
        else:
            debug_log("finish_pick without hwnd")

    def cancel(self):
        debug_log("cancel called")

        if self._closed:
            debug_log("cancel ignored because closed")
            return

        self._closed = True
        self._timer.stop()

        self._close_panes()
        self.cancelled.emit()

        debug_log("cancelled emitted")
