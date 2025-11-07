from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog, QTableWidgetItem, QHeaderView,
                               QAbstractItemView)
from Ui_PidSelect import Ui_KokoroJourney
from PySide6.QtCore import Qt
from Ui_ProcListDialog import Ui_ProcList
import psutil

class Mywindow(QMainWindow,Ui_KokoroJourney): #主窗口
    def __init__(self):
        super().__init__()  
        self.setupUi(self)
        self.pushButton_procs.clicked.connect(self.open_process_dialog)

    def open_process_dialog(self):
        dialog = DialogWindow(self) 
        result = dialog.exec()

class DialogWindow(QDialog,Ui_ProcList):
    def __init__(self, parent=None): #进程选择窗口
        super().__init__(parent)
        self.setupUi(self)
        header = self.procTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.procTable.setSortingEnabled(True)
        self.procTable.setSelectionBehavior(QAbstractItemView.SelectRows)  # 行选择
        self.procTable.setSelectionMode(QAbstractItemView.SingleSelection)  # 选择单位数量
        self.procTable.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 不可编辑
        self.pushButton_reject.clicked.connect(self.reject)
        self.populate_process_list()
    def populate_process_list(self): #进程列表填入
        processes = GetProcessList()
        self.procTable.setRowCount(len(processes))
        for row, proc_info in enumerate(processes):
            pid_item = QTableWidgetItem()
            pid_item.setData(Qt.ItemDataRole.DisplayRole, proc_info['pid'])
            name_item = QTableWidgetItem(proc_info['name'])
            path_item = QTableWidgetItem(proc_info['exe'])
            self.procTable.setItem(row, 0, pid_item)
            self.procTable.setItem(row, 1, name_item)
            self.procTable.setItem(row, 2, path_item)

def GetProcessList(): #进程获取
    attrs = ['pid', 'name', 'exe']
    process_data = []
    for proc in psutil.process_iter(attrs=attrs):
        try:
            proc_info = {
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'exe': proc.info['exe'] or 'N/A'
            }
            process_data.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return process_data

if __name__=="__main__":
    app=QApplication([])
    window=Mywindow()
    window.show()
    app.exec()