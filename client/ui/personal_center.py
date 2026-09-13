"""个人中心 → 云存档管理。

P1：手动上传/下载、版本与云端文件查看、冲突提示、单设备接管提示。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QComboBox, QFormLayout, QListWidget,
    QListWidgetItem, QDialogButtonBox,
)

from db.repository import AppRepository
from core import save_sync as ss
from core import save_bind as sb

STATUS_TEXT = {
    ss.STATUS_IN_SYNC: "与云端一致",
    ss.STATUS_LOCAL: "本地有改动",
    ss.STATUS_CLOUD: "云端有新版本",
    ss.STATUS_CONFLICT: "冲突",
    ss.STATUS_NOT_SYNCED: "尚未上传",
    sb.STATE_DELETED: "云端已删除",
    sb.STATE_NO_VERSION: "云端暂无版本",
}


class AddSaveGameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增云存档")
        self.setMinimumWidth(460)
        form = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：某游戏")
        form.addRow("名称：", self.name_edit)

        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        browse = QPushButton("浏览...")
        browse.setFixedWidth(76)
        browse.clicked.connect(self._browse)
        dir_row.addWidget(self.dir_edit, stretch=1)
        dir_row.addWidget(browse)
        form.addRow("存档目录：", dir_row)

        self.app_combo = QComboBox()
        self.app_combo.addItem("（不关联）", None)
        try:
            for a in AppRepository.get_all_apps():
                self.app_combo.addItem(a.exe_name, a.exe_path)
        except Exception:
            pass
        form.addRow("关联应用：", self.app_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择存档目录", self.dir_edit.text() or "")
        if path:
            self.dir_edit.setText(os.path.normpath(path))

    def _on_ok(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写名称。")
            return
        if not self.dir_edit.text().strip() or not os.path.isdir(self.dir_edit.text()):
            QMessageBox.warning(self, "提示", "请选择存在的存档目录。")
            return
        self.accept()

    def values(self):
        return {
            "name": self.name_edit.text().strip(),
            "local_path": os.path.normpath(self.dir_edit.text().strip()),
            "linked_app_path": self.app_combo.currentData(),
        }


class CloudVersionsDialog(QDialog):
    """查看云端版本与文件；可选择某版本回调下载。"""

    def __init__(self, parent, token: str, server_id: int, on_download=None):
        super().__init__(parent)
        self.setWindowTitle("云端版本")
        self.resize(520, 420)
        self._token = token
        self._server_id = server_id
        self._on_download = on_download
        self._versions = []

        layout = QVBoxLayout(self)
        self.version_list = QListWidget()
        self.version_list.currentRowChanged.connect(self._on_version_selected)
        layout.addWidget(QLabel("版本："))
        layout.addWidget(self.version_list)

        self.file_list = QListWidget()
        layout.addWidget(QLabel("文件："))
        layout.addWidget(self.file_list)

        row = QHBoxLayout()
        row.addStretch()
        self.btn_download = QPushButton("下载此版本")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._download)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("secondary", True)
        close_btn.clicked.connect(self.accept)
        row.addWidget(self.btn_download)
        row.addWidget(close_btn)
        layout.addLayout(row)

        self._load()

    def _load(self):
        ok, res = ss.list_versions(self._token, self._server_id)
        if not ok:
            QMessageBox.warning(self, "提示", ss_http_msg(res))
            return
        self._versions = res
        self.version_list.clear()
        for v in res:
            ts = str(v.get("createdAt") or "")[:19]
            item = QListWidgetItem(
                f"v{v['versionNumber']}  {v.get('fileCount')} 个文件  "
                f"{_fmt_size(v.get('totalSize', 0))}  {ts}"
            )
            item.setData(Qt.UserRole, v)
            self.version_list.addItem(item)

    def _on_version_selected(self, row):
        self.file_list.clear()
        if row < 0 or row >= len(self._versions):
            self.btn_download.setEnabled(False)
            return
        v = self._versions[row]
        ok, files = ss.list_version_files(self._token, self._server_id, v["id"])
        if ok:
            for f in files:
                self.file_list.addItem(f"{f['path']}  ({_fmt_size(f['size'])})")
        self.btn_download.setEnabled(True)

    def _download(self):
        row = self.version_list.currentRow()
        if row < 0 or self._on_download is None:
            return
        v = self._versions[row]
        self._on_download(v)


class CloudGamesDialog(QDialog):
    """浏览账号下的云端游戏，选择其一返回给调用方下载。"""

    def __init__(self, parent, cloud_map: dict, entries):
        super().__init__(parent)
        self.setWindowTitle("从云端获取")
        self.resize(560, 380)
        self.selected = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("当前账号下的云端游戏："))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "最新版本", "大小", "本地状态"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)

        self.games = list(cloud_map.values())
        for g in self.games:
            binding = sb.classify_cloud_binding(entries, g)
            latest = g.get("latestVersion")
            if binding == sb.BOUND_SAME:
                local_state = "已关联"
            elif binding == sb.NAME_UNBOUND:
                local_state = "本地有同名条目"
            elif binding == sb.NAME_OTHER:
                local_state = "同名冲突"
            else:
                local_state = "未关联"
            if not latest:
                local_state += " / 暂无版本"
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(g.get("name") or ""))
            self.table.setItem(r, 1, QTableWidgetItem(f"v{latest}" if latest else "—"))
            self.table.setItem(r, 2, QTableWidgetItem(_fmt_size(g.get("latestTotalSize", 0))))
            self.table.setItem(r, 3, QTableWidgetItem(local_state))

        row = QHBoxLayout()
        row.addStretch()
        self.btn_download = QPushButton("下载最新版本")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self._download)
        self.table.itemSelectionChanged.connect(self._update)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("secondary", True)
        close_btn.clicked.connect(self.reject)
        row.addWidget(self.btn_download)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _update(self):
        rows = self.table.selectionModel().selectedRows()
        self.btn_download.setEnabled(bool(rows))

    def _download(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        self.selected = self.games[rows[0].row()]
        self.accept()


class PersonalCenter(QDialog):
    def __init__(self, parent, token: str, username: str):
        super().__init__(parent)
        self.setWindowTitle("个人中心")
        self.resize(760, 460)
        self._token = token
        self._username = username
        self._cloud: dict = {}
        self._thread = None
        self._worker = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"当前账号：{username or '未登录'}"))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "本地目录", "云端最新", "状态", "关联"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2, 3, 4):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "muted")
        layout.addWidget(self.status_label)

        row = QHBoxLayout()
        self.btn_from_cloud = QPushButton("从云端获取…")
        self.btn_add = QPushButton("新增")
        self.btn_upload = QPushButton("上传本地")
        self.btn_download = QPushButton("下载云端")
        self.btn_view = QPushButton("查看云端")
        self.btn_unbind = QPushButton("解除绑定")
        self.btn_del_remote = QPushButton("删除云端")
        self.btn_del_local = QPushButton("删除本地")
        row.addWidget(self.btn_from_cloud)
        row.addWidget(self.btn_add)
        row.addStretch()
        for b in (self.btn_upload, self.btn_download, self.btn_view,
                  self.btn_unbind, self.btn_del_remote, self.btn_del_local):
            row.addWidget(b)
        layout.addLayout(row)

        self.btn_from_cloud.clicked.connect(self._open_cloud_games)
        self.btn_add.clicked.connect(self._add)
        self.btn_upload.clicked.connect(self._upload)
        self.btn_download.clicked.connect(self._download_latest)
        self.btn_view.clicked.connect(self._view_cloud)
        self.btn_unbind.clicked.connect(self._unbind)
        self.btn_del_remote.clicked.connect(self._delete_remote)
        self.btn_del_local.clicked.connect(self._delete_local)

        self.refresh()

    # ---------- 数据 ----------

    def refresh(self):
        self.status_label.setText("正在同步云端信息...")
        if self._token:
            ok, res = ss.claim_device(self._token)
            if not ok:
                self._cloud = {}
                self._populate()
                self.status_label.setText(ss_http_msg(res))
                return
            ok, res = ss.list_games(self._token)
            if not ok:
                self._cloud = {}
                self._populate()
                self.status_label.setText(ss_http_msg(res))
                return
            self._cloud = {g["id"]: g for g in res}
        self._populate()
        self.status_label.setText("")

    def _entry_status(self, entry):
        state = sb.cloud_game_state(entry, self._cloud)
        if state == sb.STATE_DELETED and entry.server_id is not None:
            return sb.STATE_DELETED, None
        if state == sb.STATE_NO_VERSION:
            return sb.STATE_NO_VERSION, None
        cloud = self._cloud.get(entry.server_id) if entry.server_id else None
        try:
            if entry.local_path and os.path.isdir(entry.local_path):
                local_changed = ss.tree_fingerprint(entry.local_path) != entry.local_fingerprint
            else:
                local_changed = True
        except Exception:
            local_changed = True
        latest = cloud.get("latestVersion") if cloud else None
        cloud_newer = bool(latest) and (entry.last_synced_version is None
                                        or latest > entry.last_synced_version)
        return ss.sync_status(local_changed, cloud_newer,
                              entry.last_synced_version is not None), latest

    def _populate(self):
        entries = AppRepository.get_all_save_games()
        self.table.setRowCount(0)
        for e in entries:
            status, latest = self._entry_status(e)
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_item = QTableWidgetItem(e.name)
            name_item.setData(Qt.UserRole, e.id)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, QTableWidgetItem(e.local_path or ""))
            self.table.setItem(r, 2, QTableWidgetItem(f"v{latest}" if latest else "—"))
            self.table.setItem(r, 3, QTableWidgetItem(STATUS_TEXT.get(status, status)))
            self.table.setItem(r, 4, QTableWidgetItem(os.path.basename(e.linked_app_path) if e.linked_app_path else "—"))
        self._update_buttons()

    def _selected_entry(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return AppRepository.get_save_game(item.data(Qt.UserRole))

    def _update_buttons(self):
        entry = self._selected_entry()
        has = entry is not None
        self.btn_upload.setEnabled(has)
        self.btn_download.setEnabled(has and entry.server_id is not None)
        self.btn_view.setEnabled(has and entry.server_id is not None)
        self.btn_del_remote.setEnabled(has and entry.server_id is not None)
        self.btn_del_local.setEnabled(has)
        deleted = has and entry.server_id is not None and entry.server_id not in self._cloud
        self.btn_unbind.setEnabled(deleted)

    # ---------- 操作 ----------

    def _open_cloud_games(self):
        entries = AppRepository.get_all_save_games()
        dlg = CloudGamesDialog(self, self._cloud, entries)
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        cloud_game = dlg.selected
        if not cloud_game.get("latestVersion"):
            QMessageBox.information(self, "提示", "云端暂无版本。")
            return

        binding = sb.classify_cloud_binding(entries, cloud_game)
        if binding == sb.NAME_OTHER:
            QMessageBox.warning(self, "冲突", "本地已有同名条目且已绑定其它云端游戏，请手动处理。")
            return

        bind_entry_id = None
        if binding == sb.BOUND_SAME:
            bound = next((e for e in entries if e.server_id == cloud_game["id"]), None)
            if bound is None:
                return
            local_path = bound.local_path
        elif binding == sb.NAME_UNBOUND:
            existing = next((e for e in entries
                             if e.name == cloud_game["name"] and e.server_id is None), None)
            if existing is None:
                return
            choice = self._ask_name_conflict(cloud_game["name"])
            if choice == "cancel":
                return
            if choice == "bind":
                bind_entry_id = existing.id
                local_path = existing.local_path
            else:
                local_path = self._choose_dir()
                if not local_path:
                    return
        else:
            local_path = self._choose_dir()
            if not local_path:
                return

        if os.path.isdir(local_path) and os.listdir(local_path):
            if QMessageBox.question(
                self, "确认覆盖",
                f"目录已有内容，将被云端版本覆盖（覆盖前会备份）：\n{local_path}\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        self._pending_bind = (cloud_game, local_path, entries, bind_entry_id)
        self._busy(True, "正在下载...")
        self._run_worker(sb.download_cloud_game_to, self._on_cloud_bind_done,
                         self._token, cloud_game, local_path, entries, bind_entry_id)

    def _ask_name_conflict(self, name):
        box = QMessageBox(self)
        box.setWindowTitle("同名条目")
        box.setText(f"本地已存在同名条目「{name}」，请选择处理方式：")
        b_bind = box.addButton("绑定已有条目", QMessageBox.AcceptRole)
        b_new = box.addButton("新建本地条目", QMessageBox.AcceptRole)
        b_cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(b_cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_bind:
            return "bind"
        if clicked is b_new:
            return "new"
        return "cancel"

    def _choose_dir(self):
        return QFileDialog.getExistingDirectory(self, "选择本地存档目录", "")

    def _on_cloud_bind_done(self, ok, res):
        self._busy(False)
        if not ok:
            if (res == ss.TAKEN_OVER and getattr(self, "_pending_bind", None)
                    and self._confirm_take_over()):
                cloud_game, local_path, entries, bind_entry_id = self._pending_bind
                self._busy(True, "正在下载...")
                self._run_worker(sb.download_cloud_game_to, self._on_cloud_bind_done,
                                 self._token, cloud_game, local_path, entries, bind_entry_id)
                return
            QMessageBox.warning(self, "下载失败", ss_http_msg(res))
            return
        QMessageBox.information(self, "完成", f"已下载并绑定，版本 v{res['version']}。")
        self.refresh()

    def _unbind(self):
        entry = self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        if QMessageBox.question(
            self, "解除绑定",
            "仅解除与云端游戏的关联，不删除本地条目和存档文件。\n是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        AppRepository.clear_save_game_server_id(entry.id)
        self.refresh()

    def _add(self):
        dlg = AddSaveGameDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if AppRepository.create_save_game(v["name"], v["local_path"], v["linked_app_path"]) is None:
            QMessageBox.warning(self, "失败", "创建本地条目失败。")
            return
        self.refresh()

    def _upload(self, entry=None):
        entry = entry or self._selected_entry()
        if entry is None:
            return
        status, _latest = self._entry_status(entry)
        if status == ss.STATUS_CONFLICT:
            reply = QMessageBox.question(
                self, "冲突",
                "本地与云端都有变化。\n是否用本地版本覆盖云端？（云端会保留历史版本）",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self._busy(True, "正在上传...")
        self._pending_upload_entry = entry
        self._run_worker(
            ss.upload_game, self._on_upload_done,
            self._token, entry.local_path, entry.name, entry.server_id)

    def _confirm_take_over(self) -> bool:
        """云端被其他设备占用时，询问是否在本机接管云同步。接管成功返回 True。"""
        reply = QMessageBox.question(
            self, "云同步被占用",
            "云端云同步当前由其他设备使用。\n是否在本机接管云同步并继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return False
        ok, res = ss.claim_device(self._token)
        if not ok:
            QMessageBox.warning(self, "接管失败", ss_http_msg(res))
            return False
        return True

    def _on_upload_done(self, ok, res):
        self._busy(False)
        if not ok:
            entry = getattr(self, "_pending_upload_entry", None)
            if res == ss.TAKEN_OVER and entry is not None and self._confirm_take_over():
                self._upload(entry)
                return
            QMessageBox.warning(self, "上传失败", ss_http_msg(res))
            return
        entry = getattr(self, "_pending_upload_entry", None)
        if entry is not None:
            if entry.server_id is None:
                AppRepository.set_save_game_server_id(entry.id, res["server_id"])
            AppRepository.mark_save_game_synced(entry.id, res["version"], res["fingerprint"])
        self.refresh()
        QMessageBox.information(self, "上传成功", f"已上传为 v{res['version']}。")

    def _download_latest(self, entry=None):
        entry = entry or self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        cloud = self._cloud.get(entry.server_id)
        latest = cloud.get("latestVersion") if cloud else None
        if not latest:
            QMessageBox.information(self, "提示", "云端暂无版本。")
            return
        self._download_version(entry, latest)

    def _download_version(self, entry, version_number):
        cloud = self._cloud.get(entry.server_id)
        # 需要 version_id：从版本列表获取
        ok, versions = ss.list_versions(self._token, entry.server_id)
        if not ok:
            QMessageBox.warning(self, "提示", ss_http_msg(versions))
            return
        target = next((v for v in versions if v["versionNumber"] == version_number), None)
        if target is None:
            QMessageBox.warning(self, "提示", "未找到该版本。")
            return
        self._busy(True, "正在下载...")
        self._pending_download = (entry, target["versionNumber"])
        self._run_worker(
            ss.prepare_download, self._on_download_done,
            self._token, entry.server_id, target["id"], entry.local_path)

    def _on_download_done(self, ok, res):
        self._busy(False)
        if not ok:
            if (res == ss.TAKEN_OVER and getattr(self, "_pending_download", None)
                    and self._confirm_take_over()):
                self._download_version(*self._pending_download)
                return
            QMessageBox.warning(self, "下载失败", ss_http_msg(res))
            return
        tmp = res
        entry, version_number = self._pending_download
        reply = QMessageBox.question(
            self, "确认覆盖",
            f"已下载并校验完成。\n是否用云端 v{version_number} 覆盖本地存档？\n"
            f"（覆盖前会先备份当前本地存档）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            ss.discard_download(tmp)
            return
        ok2, backup = ss.apply_download(tmp, entry.local_path)
        if not ok2:
            ss.discard_download(tmp)
            QMessageBox.warning(self, "覆盖失败", ss_http_msg(backup))
            return
        AppRepository.mark_save_game_synced(entry.id, version_number,
                                            ss.tree_fingerprint(entry.local_path))
        msg = f"已覆盖为 v{version_number}。"
        if backup:
            msg += f"\n原存档已备份到：{backup}"
        QMessageBox.information(self, "完成", msg)
        self.refresh()

    def _view_cloud(self):
        entry = self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        dlg = CloudVersionsDialog(
            self, self._token, entry.server_id,
            on_download=lambda v: self._download_version(entry, v["versionNumber"]))
        dlg.exec()

    def _delete_remote(self):
        entry = self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        if QMessageBox.question(self, "删除云端", "确定删除云端该游戏的存档？（本地不受影响）",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        ok, res = ss.delete_remote_game(self._token, entry.server_id)
        if not ok:
            QMessageBox.warning(self, "失败", ss_http_msg(res))
            return
        AppRepository.clear_save_game_server_id(entry.id)
        self.refresh()

    def _delete_local(self):
        entry = self._selected_entry()
        if entry is None:
            return
        if QMessageBox.question(self, "删除本地条目", "确定删除该本地条目？（不删除本地文件与云端）",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        AppRepository.delete_save_game(entry.id)
        self.refresh()

    # ---------- 后台线程 ----------

    def _busy(self, busy: bool, text: str = ""):
        for b in (self.btn_from_cloud, self.btn_add, self.btn_upload, self.btn_download,
                  self.btn_view, self.btn_unbind, self.btn_del_remote, self.btn_del_local):
            b.setEnabled(not busy)
        if text:
            self.status_label.setText(text)
        if not busy:
            self._update_buttons()

    def _run_worker(self, fn, on_done, *args):
        self._thread = QThread(self)
        self._worker = ss.SaveSyncWorker(fn, *args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_progress(self, done, total, label):
        self.status_label.setText(f"{label} {done}/{total}")

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "正在同步中，请稍候。")
            event.ignore()
            return
        super().closeEvent(event)


def _fmt_size(n):
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0


def ss_http_msg(res) -> str:
    if res == ss.TAKEN_OVER:
        return "云同步已由其他设备接管。"
    return str(res)


def dlg_close(dlg):
    try:
        dlg.close()
    except Exception:
        pass
