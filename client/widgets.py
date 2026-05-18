from PySide6.QtWidgets import QComboBox


class AlwaysDownComboBox(QComboBox):
    """下拉框：点击时总是向下展开列表，不根据屏幕空间自动向上弹出。"""

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QComboBox)
        if popup is None and self.view() and self.view().window():
            popup_geo = self.view().window().geometry()
            new_y = self.mapToGlobal(self.rect().bottomLeft()).y()
            self.view().window().move(popup_geo.x(), new_y)
