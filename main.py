from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog,QTableWidgetItem,
                               QHeaderView, QAbstractItemView)
from Ui_PidSelect import Ui_KokoroJourney
from PySide6.QtCore import Qt
from Ui_ProcListDialog import Ui_ProcList
import psutil
import os

class Mywindow(QMainWindow,Ui_KokoroJourney): #主窗口
    def __init__(self):
        super().__init__()  
        self.setupUi(self)
        self.pushButton_procs.clicked.connect(self.open_process_dialog)
        self.proc_name_show.setText("尚未选择进程") 
        self.proc_path_show.setText("尚未选择进程") 
    def open_process_dialog(self):  # 打开选择窗口并获取进程信息
        dialog = DialogWindow(self) 
        result = dialog.exec()
        if result == QDialog.Accepted:
            self.proc_pid = dialog.proc_pid
            self.proc_name = dialog.proc_name
            self.proc_path = dialog.proc_path
            # self.pid_show.setText(self.selected_pid)
            self.proc_name_show.setText(self.proc_name)
            self.proc_path_show.setText(self.proc_path)
        else:
            print("用户取消了选择。") 
class DialogWindow(QDialog,Ui_ProcList):
    def __init__(self, parent=None): #进程选择窗口
        super().__init__(parent)
        self.setupUi(self)
        self.proc_pid = None
        self.proc_name = None
        self.proc_path = None
        header = self.procTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.procTable.setSortingEnabled(True)  # 启用排序
        self.procTable.setSelectionBehavior(QAbstractItemView.SelectRows)  # 行选择
        self.procTable.setSelectionMode(QAbstractItemView.SingleSelection)  # 选择单位数量
        self.procTable.setEditTriggers(QAbstractItemView.NoEditTriggers)  # 不可编辑
        self.pushButton_accept.clicked.connect(self.get_proc_info_and_aceept)
        self.pushButton_reject.clicked.connect(self.reject)
        self.populate_process_list()
    def populate_process_list(self): #进程列表填入
        processes = get_process_list()
        self.procTable.setRowCount(len(processes))
        for row, proc_info in enumerate(processes):
            pid_item = QTableWidgetItem()
            pid_item.setData(Qt.ItemDataRole.DisplayRole, proc_info['pid'])
            pid_item.setToolTip(str(proc_info['pid']))
            name_item = QTableWidgetItem(proc_info['name'])
            name_item.setToolTip(proc_info['name'])
            path_item = QTableWidgetItem(proc_info['exe'])
            path_item.setToolTip(proc_info['exe'])
            
            self.procTable.setItem(row, 0, pid_item)
            self.procTable.setItem(row, 1, name_item)
            self.procTable.setItem(row, 2, path_item)
    def get_proc_info_and_aceept(self): #获取进程信息并接受
        selected_rows_indexes = self.procTable.selectionModel().selectedRows()
        if not selected_rows_indexes:
            print("没有选中的行。")
            return None, None
        first_selected_row_index = selected_rows_indexes[0]
        row = first_selected_row_index.row()
        pid = self.procTable.item(row, 0).text()
        name = self.procTable.item(row, 1).text()
        path = self.procTable.item(row, 2).text()
        self.proc_pid = pid
        self.proc_name = name
        self.proc_path = path
        print(f"对话框内部已存储 -> PID: {self.proc_pid},\
                进程名: {self.proc_name}, \
                路径: {self.proc_path}")
        self.accept()
    
        
def get_process_list(): #进程获取
    attrs = ['pid', 'name', 'exe']
    process_data = []
    path_separator = os.sep
    for proc in psutil.process_iter(attrs=attrs):
        try:
            proc_info = {
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'exe': proc.info['exe'] or 'N/A'
            }
            if not proc_info['exe']:
                continue
            if path_separator not in proc_info['exe']:
                continue
            if proc_info['pid'] in [0, 4]:
                continue
            process_data.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return process_data

if __name__=="__main__":
    app=QApplication([])
    window=Mywindow()
    window.show()
    app.exec()
