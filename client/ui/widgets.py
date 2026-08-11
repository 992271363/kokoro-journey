from PySide6.QtWidgets import QComboBox, QLineEdit


class AlwaysDownComboBox(QComboBox):
    """下拉框：点击时总是向下展开列表，不根据屏幕空间自动向上弹出。"""

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QComboBox)
        if popup is None and self.view() and self.view().window():
            popup_geo = self.view().window().geometry()
            new_y = self.mapToGlobal(self.rect().bottomLeft()).y()
            self.view().window().move(popup_geo.x(), new_y)


from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QSizeGrip


class StyledSizeGrip(QSizeGrip):
    _DOT_COLOR_LIGHT = QColor(0x94, 0xA3, 0xB8)
    _DOT_COLOR_DARK = QColor(0x64, 0x74, 0x8B)
    _DOT_RADIUS = 2
    _DOT_SPACING = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._is_dark = False

    def set_dark_mode(self, is_dark: bool):
        self._is_dark = is_dark
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._DOT_COLOR_DARK if self._is_dark else self._DOT_COLOR_LIGHT)

        w = self.width()
        h = self.height()
        d = self._DOT_RADIUS * 2
        s = self._DOT_SPACING

        painter.drawEllipse(w - 5, h - 5, d, d)
        painter.drawEllipse(w - 5 - s, h - 5, d, d)
        painter.drawEllipse(w - 5, h - 5 - s, d, d)

        painter.end()


class ChineseMenuLineEdit(QLineEdit):
    """QLineEdit 右键菜单中文化基类。

    PySide6 中 Qt 构建标准菜单时不会把 createStandardContextMenu()
    分派回 Python 重写，因此须再重写 contextMenuEvent 主动调用它。
    """

    _MENU_TRANSLATIONS = {
        "Undo": "撤销",
        "Redo": "重做",
        "Cut": "剪切",
        "Copy": "复制",
        "Paste": "粘贴",
        "Delete": "删除",
        "Select All": "全选",
    }

    def createStandardContextMenu(self):
        menu = super().createStandardContextMenu()
        for action in menu.actions():
            text = action.text().replace("&", "").split("\t")[0]
            if text in self._MENU_TRANSLATIONS:
                action.setText(self._MENU_TRANSLATIONS[text])
        return menu

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
