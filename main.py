from PySide6.QtWidgets import QApplication, QMainWindow, QDialog, QTableWidgetItem, QHeaderView
from Ui_PidSelect import Ui_KokoroJourney
from Ui_ProcListDialog import Ui_ProcList
import psutil

class Mywindow(QMainWindow,Ui_KokoroJourney):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.pushButton_procs.clicked.connect(self.open_process_dialog)
        
    def open_process_dialog(self):
        dialog = DialogWindow(self) 
        result = dialog.exec()

class DialogWindow(QDialog,Ui_ProcList):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        header = self.procTable.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.pushButton_reject.clicked.connect(self.reject)
        self.populate_process_list()
        self.pushButton_reject.clicked.connect(self.reject)

    def populate_process_list(self):
        processes = GetProcessList()
        self.procTable.setRowCount(len(processes))
        for row, proc_info in enumerate(processes):
            pid_str = str(proc_info['pid'])
            pid_item = QTableWidgetItem(pid_str)
            name_item = QTableWidgetItem(proc_info['name'])
            path_item = QTableWidgetItem(proc_info['exe'])
            self.procTable.setItem(row, 0, pid_item)
            self.procTable.setItem(row, 1, name_item)
            self.procTable.setItem(row, 2, path_item)

def GetProcessList():
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