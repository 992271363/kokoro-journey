import webbrowser

from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import (
    QDialog, QPushButton, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout,
    QFormLayout, QComboBox, QCheckBox
)

from core.api import api_login, LoginStatus, BASE_URL
from util import credentials


class LoginWorker(QObject):
    finished = Signal(LoginStatus, str)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password

    def run(self):
        print("LoginWorker: 开始在后台线程中执行登录...")
        status, token = api_login(self.username, self.password)
        self.finished.emit(status, token)
        print("LoginWorker: 任务完成，已发出 finished 信号。")


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录")
        self.setFixedSize(320, 300)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(12)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)

        # 账号：可编辑下拉 + 删除按钮
        account_row = QHBoxLayout()
        account_row.setSpacing(4)
        self.user_combo = QComboBox()
        self.user_combo.setEditable(True)
        self.user_combo.setInsertPolicy(QComboBox.NoInsert)
        self.user_combo.addItems(credentials.get_accounts())
        account_row.addWidget(self.user_combo, stretch=1)
        self.btn_del_account = QPushButton("x")
        self.btn_del_account.setFixedWidth(28)
        self.btn_del_account.setToolTip("从账号历史中删除当前账号")
        self.btn_del_account.setProperty("secondary", True)
        self.btn_del_account.clicked.connect(self._delete_current_account)
        account_row.addWidget(self.btn_del_account)
        form_layout.addRow("账号：", account_row)

        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        form_layout.addRow("密码：", self.pass_input)

        main_layout.addLayout(form_layout)

        # 记住密码 / 自动登录
        self.check_remember = QCheckBox("记住密码")
        self.check_auto_login = QCheckBox("自动登录")
        remember = bool(credentials.Settings().get("rememberPassword", False))
        auto = credentials.is_auto_login()
        self.check_remember.setChecked(remember or auto)
        self.check_auto_login.setChecked(auto)
        self.check_auto_login.toggled.connect(self._on_auto_login_toggled)
        opt_row = QHBoxLayout()
        opt_row.addWidget(self.check_remember)
        opt_row.addWidget(self.check_auto_login)
        opt_row.addStretch()
        main_layout.addLayout(opt_row)

        # 确认 / 取消
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        self.login_accept = QPushButton("确认")
        self.login_reject = QPushButton("取消")
        self.login_reject.setProperty("secondary", True)
        btn_layout.addStretch()
        btn_layout.addWidget(self.login_accept)
        btn_layout.addWidget(self.login_reject)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # 前往注册
        reg_layout = QHBoxLayout()
        self.register_button = QPushButton("前往注册")
        self.register_button.setProperty("secondary", True)
        reg_layout.addStretch()
        reg_layout.addWidget(self.register_button)
        reg_layout.addStretch()
        main_layout.addLayout(reg_layout)

        self.tips_label = QLabel("", self)
        self.tips_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.tips_label)

        self.token = None
        self.username = None
        self.worker_thread = None

        self.login_accept.clicked.connect(self.attempt_login)
        self.login_reject.clicked.connect(self.reject)
        self.register_button.clicked.connect(self._open_register_page)
        self.user_combo.currentTextChanged.connect(self._on_account_changed)

        # 预填密码
        self._on_account_changed(self.user_combo.currentText())

    # ---- 账号历史 ----

    def _on_account_changed(self, text):
        if not self.check_remember.isChecked():
            return
        pwd = credentials.get_password(text.strip()) if text.strip() else None
        if pwd is not None:
            self.pass_input.setText(pwd)

    def _delete_current_account(self):
        name = self.user_combo.currentText().strip()
        if not name:
            return
        credentials.remove_account(name)
        current = self.user_combo.currentText()
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItems(credentials.get_accounts())
        self.user_combo.setCurrentText(credentials.get_accounts()[0] if credentials.get_accounts() else "")
        self.user_combo.blockSignals(False)
        self.pass_input.clear()

    def _on_auto_login_toggled(self, checked):
        if checked:
            self.check_remember.setChecked(True)

    # ---- 登录 ----

    def attempt_login(self):
        username_text = self.user_combo.currentText().strip()
        password_text = self.pass_input.text()

        if not username_text or not password_text:
            self.tips_label.setText("用户名和密码不能为空。")
            return

        self.login_accept.setEnabled(False)
        self.tips_label.setText("正在登录中，请稍候...")

        self.worker_thread = QThread()
        self.worker = LoginWorker(username_text, password_text)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_login_result)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        print(f"LoginDialog: 启动登录线程, username={username_text}")
        self.worker_thread.start()

    def handle_login_result(self, status, token):
        print(f"LoginDialog: 已收到后台结果 -> Status: {status}, Token: {'Yes' if token else 'No'}")
        self.login_accept.setEnabled(True)

        if status == LoginStatus.SUCCESS:
            self.token = token
            self.username = self.user_combo.currentText().strip()
            self._persist_credentials()
            print(f"LoginDialog: 即将调用 accept(), username={self.username}")
            self.accept()
        elif status == LoginStatus.INVALID_CREDENTIALS:
            self.tips_label.setText("用户名或密码不正确。")
        elif status == LoginStatus.NETWORK_ERROR:
            self.tips_label.setText("网络错误，无法连接到服务器。")
        else:
            self.tips_label.setText("发生未知错误，请稍后重试。")

    def _persist_credentials(self):
        username = self.username
        password = self.pass_input.text()
        credentials.add_account(username)
        credentials.Settings().set("rememberPassword", self.check_remember.isChecked())
        if self.check_remember.isChecked():
            credentials.save_password(username, password)
        else:
            credentials.clear_password(username)
        credentials.set_auto_login(self.check_auto_login.isChecked(), username)

    def _open_register_page(self):
        register_url = f"{BASE_URL}/register"
        webbrowser.open(register_url)

    def closeEvent(self, event):
        if hasattr(self, 'worker_thread') and self.worker_thread and self.worker_thread.isRunning():
            print("LoginDialog: 用户关闭窗口，正在尝试停止仍在运行的登录线程...")
            self.worker_thread.quit()
            self.worker_thread.wait(200)
        super().closeEvent(event)
