import os
import sys
import psutil, datetime, time
from PySide6.QtCore import Qt, QObject, Signal, QThread
from PySide6.QtWidgets import (QApplication, QMainWindow, QDialog,QTableWidgetItem,
                               QHeaderView, QAbstractItemView)

from Ui_PidSelect import Ui_KokoroJourney
from Ui_ProcListDialog import Ui_ProcList


class ProcessMonitorWorker(QObject):
    process_terminated = Signal(int, str)
    error_occurred = Signal(str)
    finished = Signal()
    def __init__(self, pid_to_watch):
        super().__init__()
        self._pid = pid_to_watch
        self._is_running = True
    def run_check(self):
        try:
            if not psutil.pid_exists(self._pid):
                self.error_occurred.emit(f"进程 {self._pid} 在监视开始前就不存在。")
                return
            while self._is_running and psutil.pid_exists(self._pid):
                time.sleep(1)
            if self._is_running:
                death_time_str = datetime.datetime.now()
                year = death_time_str.year
                month = death_time_str.month
                day = death_time_str.day
                time_str = death_time_str.strftime("%H:%M:%S")
                end_time_str = f"{year}年{month:02d}月{day:02d}日 {time_str}"
                self.process_terminated.emit(self._pid, end_time_str)
        except Exception as e:
            self.error_occurred.emit(f"监视 PID {self._pid} 时发生意外错误: {e}")
    def stop(self):
        self._is_running = False

class Mywindow(QMainWindow,Ui_KokoroJourney):
    def __init__(self):
        super().__init__()  
        self.setupUi(self)
        self.proc_pid = None
        self.monitor_thread = None
        self.worker = None
        
        self.pushButton_procs.clicked.connect(self.open_process_dialog)
        self.proc_name_show.setText("尚未选择进程") 
        self.proc_path_show.setText("尚未选择进程") 
        self.proc_start_time_show.setText("尚未选择进程")
        self.proc_end_time_show.setText("尚未选择进程")
    def open_process_dialog(self):
        dialog = DialogWindow(self)
        if dialog.exec() == QDialog.Accepted:
            selected_pid = dialog.get_selected_pid()
            if selected_pid:
                self.update_proc_info(selected_pid)
                self.start_monitoring_process(selected_pid)
    def update_proc_info(self, pid):
        try:
            proc = psutil.Process(pid)
            self.proc_pid = pid
            self.proc_name_show.setText(proc.name())
            self.proc_path_show.setText(proc.exe())
            
            create_time = datetime.datetime.fromtimestamp(proc.create_time())
            year = create_time.year
            month = create_time.month
            day = create_time.day
            time_str = create_time.strftime("%H:%M:%S")
            self.create_time_str = f"{year}年{month:02d}月{day:02d}日 {time_str}"
            self.proc_start_time_show.setText(self.create_time_str)
            self.proc_end_time_show.setText("监视中...") 
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.proc_name_show.setText(f"无法访问进程 {pid}")
            self.proc_path_show.setText("N/A")
            self.proc_start_time_show.setText("N/A")
            self.proc_end_time_show.setText("N/A")
    def start_monitoring_process(self, pid):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.worker.stop()
            self.monitor_thread.quit()
            self.monitor_thread.wait()
        self.monitor_thread = QThread()
        self.worker = ProcessMonitorWorker(pid)
        self.worker.moveToThread(self.monitor_thread)
        self.monitor_thread.started.connect(self.worker.run_check)
        self.worker.process_terminated.connect(self.on_process_terminated)
        self.worker.error_occurred.connect(self.on_monitor_error)
        self.monitor_thread.finished.connect(self.on_monitor_finished)
        self.monitor_thread.finished.connect(self.worker.deleteLater)
        self.monitor_thread.start()
    def on_process_terminated(self, pid, end_time_str):
        if self.proc_pid != pid:
            print(f"[Manager] 这是一个过时的报告，忽略。")
            return
        self.proc_end_time_show.setText(end_time_str)
    def on_monitor_finished(self):
        print("[Manager] 确认监视线程已结束。")
    def on_monitor_error(self, error_message):
        print(f"[Manager] 接到错误报告: {error_message}")
    def closeEvent(self, event):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.worker.stop()
            self.monitor_thread.quit()
            self.monitor_thread.wait()
        super().closeEvent(event)
    def get_create_timestamp(self,pid):
        proc = psutil.Process(pid)
        create_timestamp = proc.create_time()
        create_datetime = datetime.datetime.fromtimestamp(create_timestamp)
        return create_datetime

class DialogWindow(QDialog,Ui_ProcList):
    def __init__(self, parent=None):
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
        self.pushButton_accept.clicked.connect(self.accept) # 直接接受
        self.pushButton_reject.clicked.connect(self.reject)
        self.populate_process_list()
    def get_selected_pid(self): 
        selected_rows_indexes = self.procTable.selectionModel().selectedRows()
        if not selected_rows_indexes:
            return None
        row = selected_rows_indexes[0].row()
        return self.procTable.item(row, 0).data(Qt.ItemDataRole.UserRole)
    def populate_process_list(self):
        processes = get_process_list()
        self.procTable.setRowCount(len(processes))
        for row, proc_info in enumerate(processes):
            pid_item = QTableWidgetItem()
            pid_item.setData(Qt.ItemDataRole.DisplayRole, proc_info['pid'])
            pid_item.setData(Qt.ItemDataRole.UserRole, proc_info['pid'])
            pid_item.setToolTip(str(proc_info['pid']))
            name_item = QTableWidgetItem(proc_info['name'])
            name_item.setToolTip(proc_info['name'])
            path_item = QTableWidgetItem(proc_info['exe'])
            path_item.setToolTip(proc_info['exe'])
            
            self.procTable.setItem(row, 0, pid_item)
            self.procTable.setItem(row, 1, name_item)
            self.procTable.setItem(row, 2, path_item)
    

def get_process_list():
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
    app=QApplication(sys.argv)
    window=Mywindow()
    window.show()
    sys.exit(app.exec())
