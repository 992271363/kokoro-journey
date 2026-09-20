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
    QMessageBox, QFileDialog, QFormLayout, QListWidget,
    QListWidgetItem, QDialogButtonBox,
    QFrame, QGridLayout, QRadioButton, QButtonGroup, QStackedWidget,
)

from db.repository import AppRepository, AppInfo
from core import save_sync as ss
from core import save_bind as sb
from ui.widgets import ChineseMenuLineEdit
from util.search import make_search_keywords, matches_search_keywords

STATUS_TEXT = {
    ss.STATUS_IN_SYNC: "与云端一致",
    ss.STATUS_LOCAL: "本地有改动",
    ss.STATUS_CLOUD: "云端有新版本",
    ss.STATUS_CONFLICT: "冲突",
    ss.STATUS_NOT_SYNCED: "尚未上传云端",
    sb.STATE_DELETED: "云端已删除",
    sb.STATE_NO_VERSION: "云端暂无版本",
}


class AppPickDialog(QDialog):
    """选择关联应用：搜索 + 排序（参考 ProcSelectDialog）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择关联应用")
        self.resize(564, 429)

        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["应用名", "路径", "最近启动"])
        layout.addWidget(self.table)

        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        self.search_edit = ChineseMenuLineEdit()
        self.search_edit.setMaximumSize(155, 16777215)
        self.search_edit.setAlignment(Qt.AlignCenter)
        self.search_edit.setPlaceholderText("搜索")
        toolbar.addWidget(self.search_edit)
        layout.addLayout(toolbar)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_ok = QPushButton("确认")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setProperty("secondary", True)
        bottom.addWidget(self.btn_ok)
        bottom.addWidget(self.btn_cancel)
        layout.addLayout(bottom)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        self._apps: list = []
        self.search_edit.textChanged.connect(self._populate)
        self.btn_refresh.clicked.connect(self._load)
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        self.table.doubleClicked.connect(lambda *_: self._on_ok())

        self._load()

    def _load(self):
        try:
            self._apps = AppRepository.get_all_apps()
        except Exception:
            self._apps = []
        self._populate()

    def _populate(self, *_):
        keywords = make_search_keywords(self.search_edit.text())
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        rows = self._apps
        if keywords:
            rows = [a for a in rows
                    if matches_search_keywords([a.exe_name, a.exe_path], keywords)]
        self.table.setRowCount(len(rows))
        for r, a in enumerate(rows):
            name_item = QTableWidgetItem(a.exe_name)
            name_item.setData(Qt.UserRole, a.exe_path)
            name_item.setToolTip(a.exe_name)
            path_item = QTableWidgetItem(a.exe_path)
            path_item.setToolTip(a.exe_path)
            last_item = QTableWidgetItem(a.last_start_at)
            last_item.setData(Qt.UserRole, a.last_start_at_ts)
            last_item.setToolTip(a.last_start_at)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, path_item)
            self.table.setItem(r, 2, last_item)
        self.table.setSortingEnabled(True)

    def selected_app(self) -> Optional[AppInfo]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        exe_path = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        return next((a for a in self._apps if a.exe_path == exe_path), None)

    def _on_ok(self):
        if self.selected_app() is None:
            QMessageBox.warning(self, "提示", "请选择一个应用。")
            return
        self.accept()


class AddSaveGameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建本地存档条目")
        self.setMinimumWidth(460)
        form = QFormLayout(self)

        self._linked_path = None
        self._linked_name = ""
        self._name_edited = False

        # 1) 关联应用（可选）
        app_row = QHBoxLayout()
        self.app_edit = QLineEdit()
        self.app_edit.setReadOnly(True)
        self.app_edit.setPlaceholderText("（可选）选择关联应用")
        btn_pick = QPushButton("选择...")
        btn_pick.setFixedWidth(76)
        btn_pick.clicked.connect(self._pick_app)
        btn_clear = QPushButton("清除")
        btn_clear.setFixedWidth(60)
        btn_clear.clicked.connect(self._clear_app)
        app_row.addWidget(self.app_edit, stretch=1)
        app_row.addWidget(btn_pick)
        app_row.addWidget(btn_clear)
        form.addRow("关联应用：", app_row)

        # 2) 名称（选择应用后预填应用名；用户手改后不再覆盖）
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：某游戏")
        self.name_edit.textEdited.connect(self._on_name_edited)
        form.addRow("名称：", self.name_edit)

        # 3) 存档目录
        dir_row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        browse = QPushButton("浏览...")
        browse.setFixedWidth(76)
        browse.clicked.connect(self._browse)
        dir_row.addWidget(self.dir_edit, stretch=1)
        dir_row.addWidget(browse)
        form.addRow("存档目录：", dir_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_name_edited(self, _text):
        self._name_edited = True

    def _pick_app(self):
        dlg = AppPickDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        app = dlg.selected_app()
        if app is not None:
            self._apply_app(app.exe_path, app.exe_name)

    def _apply_app(self, exe_path, exe_name):
        self._linked_path = exe_path
        self._linked_name = exe_name
        self.app_edit.setText(exe_name)
        if not self._name_edited:
            self.name_edit.setText(exe_name)

    def _clear_app(self):
        self._linked_path = None
        self._linked_name = ""
        self.app_edit.clear()

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
            "linked_app_path": self._linked_path,
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
        self.btn_download = QPushButton("下载并覆盖本地")
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
        self.setWindowTitle("从云端导入")
        self.resize(560, 380)
        self.selected = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("当前账号下的云端游戏："))

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "云端版本", "大小", "本地关联"])
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
        self.btn_download = QPushButton("导入到本地…")
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


class SlotCard(QFrame):
    """存档位卡片：左上角单选圆点，卡内显示上传时间/文件大小；空槽用常规样式。"""

    def __init__(self, slot: int, info, parent=None):
        super().__init__(parent)
        self.slot = slot
        occupied = bool(info and info.get("versionId"))
        self.setObjectName("slot_card")
        self.setProperty("slot_occupied", occupied)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)

        self.radio = QRadioButton(f"存档位 {slot}")
        self.radio.setObjectName("slot_radio")
        layout.addWidget(self.radio)

        if occupied:
            ts = str(info.get("createdAt") or "")[:19].replace("T", " ")
            self.time_label = QLabel(ts or "—")
            self.size_label = QLabel(_fmt_size(info.get("totalSize", 0)))
        else:
            self.time_label = QLabel("空")
            self.size_label = QLabel("")
        for lbl in (self.time_label, self.size_label):
            lbl.setProperty("role", "muted")
            layout.addWidget(lbl)
        layout.addStretch()

    def mousePressEvent(self, event):
        self.radio.setChecked(True)
        super().mousePressEvent(event)


class SlotPickerDialog(QDialog):
    """存档位选择：每页 5 个、共 2 页；单选；上传/下载/查看三种用途共用。"""

    _TEXT = {
        "upload": ("选择上传存档位", "选择一个存档位写入本地存档；已占用的槽位会被覆盖。"),
        "download": ("选择下载存档位", "选择一个存档位下载到本地；将覆盖本地存档（覆盖前会备份）。"),
        "view": ("查看清单", "选择要查看文件清单的存档位。"),
    }

    def __init__(self, parent, slots, mode: str = "upload"):
        super().__init__(parent)
        title, desc = self._TEXT.get(mode, self._TEXT["upload"])
        self.setWindowTitle(title)
        self.resize(560, 360)
        self.mode = mode
        self.selected = None
        self._slots = {s.get("slot"): s for s in (slots or [])}

        layout = QVBoxLayout(self)
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        self._pages = QStackedWidget()
        layout.addWidget(self._pages, stretch=1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        page_size = ss.SLOT_PAGE_SIZE
        total = ss.SLOT_COUNT
        self._page_count = (total + page_size - 1) // page_size
        for p in range(self._page_count):
            page = QFrame()
            grid = QGridLayout(page)
            grid.setSpacing(8)
            for col in range(page_size):
                slot = p * page_size + col + 1
                if slot > total:
                    break
                card = SlotCard(slot, self._slots.get(slot))
                self._group.addButton(card.radio, slot)
                grid.addWidget(card, 0, col)
            self._pages.addWidget(page)

        self._group.buttonToggled.connect(self._on_toggled)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("上一页")
        self.btn_next = QPushButton("下一页")
        self.btn_prev.clicked.connect(lambda: self._goto(self._pages.currentIndex() - 1))
        self.btn_next.clicked.connect(lambda: self._goto(self._pages.currentIndex() + 1))
        nav.addWidget(self.btn_prev)
        self.page_label = QLabel("")
        nav.addWidget(self.page_label)
        nav.addWidget(self.btn_next)
        nav.addStretch()
        layout.addLayout(nav)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._goto(0)

    def _goto(self, index: int):
        index = max(0, min(self._page_count - 1, index))
        self._pages.setCurrentIndex(index)
        self.page_label.setText(f"{index + 1} / {self._page_count}")
        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setEnabled(index < self._page_count - 1)

    def _on_toggled(self, button, checked):
        if checked:
            self.selected = self._group.id(button)

    def _on_ok(self):
        if self.selected is None:
            QMessageBox.information(self, "提示", "请选择一个存档位。")
            return
        self.accept()

    def selected_slot(self):
        return self.selected

    def selected_info(self):
        return self._slots.get(self.selected)


class SlotFilesDialog(QDialog):
    """查看某个存档位（版本）的文件清单。"""

    def __init__(self, parent, token, server_id, version_id, slot=None):
        super().__init__(parent)
        self.setWindowTitle(f"存档位 {slot} 文件清单" if slot else "文件清单")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        ok, files = ss.list_version_files(token, server_id, version_id)
        if not ok:
            self.file_list.addItem(ss_http_msg(files))
        else:
            for f in files:
                self.file_list.addItem(f"{f['path']}  ({_fmt_size(f['size'])})")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PersonalCenter(QDialog):
    def __init__(self, parent, token: str, username: str):
        super().__init__(parent)
        self.setWindowTitle("云存档")
        self.resize(760, 460)
        self._token = token
        self._username = username
        self._cloud: dict = {}
        self._slots: dict = {}
        self._thread = None
        self._worker = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"当前账号：{username or '未登录'}"))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "存档目录", "云端版本", "状态", "关联应用"])
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

        self.btn_from_cloud = QPushButton("从云端导入…")
        self.btn_from_cloud.setToolTip("把账号下的云端游戏下载到本机并建立关联（新设备/首次）")
        self.btn_add = QPushButton("新建目录")
        self.btn_add.setToolTip("在本地登记一个存档目录（对应一个本地条目，尚未上传云端）")
        self.btn_upload = QPushButton("上传到云端")
        self.btn_upload.setToolTip("用本地存档新建一个云端版本（不改本地文件）")
        self.btn_download = QPushButton("下载到本地")
        self.btn_download.setToolTip("下载云端最新版本并覆盖本地（覆盖前自动备份）")
        self.btn_view = QPushButton("查看清单…")
        self.btn_view.setToolTip("查看某个存档位内的文件清单")
        self.btn_unbind = QPushButton("解除云端关联")
        self.btn_unbind.setToolTip("只解除关联，不删除本地文件与云端存档")
        self.btn_del_remote = QPushButton("删除云端存档")
        self.btn_del_remote.setToolTip("删除账号下的云端存档（本地不受影响）")
        self.btn_del_local = QPushButton("删除目录")
        self.btn_del_local.setToolTip("仅删除本地条目，不删除磁盘上的存档目录，也不影响云端存档")

        row1 = QHBoxLayout()
        for b in (self.btn_from_cloud, self.btn_add, self.btn_upload, self.btn_download):
            row1.addWidget(b)
        row1.addStretch()
        row2 = QHBoxLayout()
        for b in (self.btn_view, self.btn_unbind, self.btn_del_remote, self.btn_del_local):
            row2.addWidget(b)
        row2.addStretch()
        layout.addLayout(row1)
        layout.addLayout(row2)

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
                self._slots = {}
                self._populate()
                self.status_label.setText(ss_http_msg(res))
                return
            ok, res = ss.list_games(self._token)
            if not ok:
                self._cloud = {}
                self._slots = {}
                self._populate()
                self.status_label.setText(ss_http_msg(res))
                return
            self._cloud = {g["id"]: g for g in res}
            slots = {}
            for gid in self._cloud:
                ok2, sl = ss.list_slots(self._token, gid)
                slots[gid] = sl if ok2 else []
            self._slots = slots
        self._populate()
        self.status_label.setText("")

    def _game_slots(self, server_id):
        return getattr(self, "_slots", {}).get(server_id, []) or []

    def _entry_status(self, entry):
        if entry.server_id is None:
            return ss.STATUS_NOT_SYNCED, None
        if entry.server_id not in self._cloud:
            return sb.STATE_DELETED, None
        slot_info = next((s for s in self._game_slots(entry.server_id)
                          if s.get("slot") == entry.server_slot), None)
        if slot_info is None or not slot_info.get("versionId"):
            return sb.STATE_NO_VERSION, None
        try:
            if entry.local_path and os.path.isdir(entry.local_path):
                local_changed = ss.tree_fingerprint(entry.local_path) != entry.local_fingerprint
            else:
                local_changed = True
        except Exception:
            local_changed = True
        cloud_newer = slot_info.get("versionId") != entry.last_synced_version
        return ss.sync_status(local_changed, cloud_newer,
                              entry.last_synced_version is not None), slot_info.get("versionId")

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
            QMessageBox.warning(self, "冲突", "本地已有同名条目且已关联其它云端游戏，请手动处理。")
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

        ok, slots = ss.list_slots(self._token, cloud_game["id"])
        if not ok:
            QMessageBox.warning(self, "提示", ss_http_msg(slots))
            return
        picker = SlotPickerDialog(self, slots, mode="download")
        if picker.exec() != QDialog.Accepted:
            return
        info = picker.selected_info() or {}
        if not info.get("versionId"):
            QMessageBox.information(self, "提示", "该存档位为空。")
            return

        self._pending_bind = (cloud_game, local_path, entries, bind_entry_id,
                              picker.selected_slot(), info.get("versionId"))
        self._busy(True, "正在下载...")
        self._run_worker(sb.download_cloud_game_to, self._on_cloud_bind_done,
                         self._token, cloud_game, local_path, entries, bind_entry_id,
                         picker.selected_slot(), info.get("versionId"))

    def _ask_name_conflict(self, name):
        box = QMessageBox(self)
        box.setWindowTitle("同名条目")
        box.setText(f"本地已存在同名条目「{name}」，请选择处理方式：")
        b_bind = box.addButton("关联已有条目", QMessageBox.AcceptRole)
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
                self._busy(True, "正在下载...")
                self._run_worker(sb.download_cloud_game_to, self._on_cloud_bind_done,
                                 self._token, *self._pending_bind)
                return
            QMessageBox.warning(self, "下载失败", ss_http_msg(res))
            return
        QMessageBox.information(self, "完成", f"已下载并关联（存档位 {res.get('slot')}）。")
        self.refresh()

    def _unbind(self):
        entry = self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        if QMessageBox.question(
            self, "解除云端关联",
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
        slots = self._game_slots(entry.server_id) if entry.server_id is not None else []
        if not slots:
            slots = [{"slot": i, "versionId": None, "createdAt": None,
                      "totalSize": None, "fileCount": None}
                     for i in range(1, ss.SLOT_COUNT + 1)]

        dlg = SlotPickerDialog(self, slots, mode="upload")
        if dlg.exec() != QDialog.Accepted:
            return
        slot = dlg.selected_slot()
        info = dlg.selected_info() or {}
        if info.get("versionId"):
            ts = str(info.get("createdAt") or "")[:19].replace("T", " ")
            if QMessageBox.question(
                self, "覆盖存档位",
                f"存档位 {slot} 已有存档（{ts}，{_fmt_size(info.get('totalSize', 0))}）。\n"
                f"继续将覆盖该存档位，是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        status, _ = self._entry_status(entry)
        if status == ss.STATUS_CONFLICT:
            reply = QMessageBox.question(
                self, "冲突",
                "本地与绑定的存档位都有变化。\n是否用本地版本覆盖所选存档位？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self._busy(True, "正在上传...")
        self._pending_upload_entry = entry
        self._pending_upload_slot = slot
        self._run_worker(
            ss.upload_game, self._on_upload_done,
            self._token, entry.local_path, entry.name, entry.server_id, slot)

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
        entry = getattr(self, "_pending_upload_entry", None)
        if not ok:
            if res == ss.TAKEN_OVER and entry is not None and self._confirm_take_over():
                self._upload(entry)
                return
            QMessageBox.warning(self, "上传失败", ss_http_msg(res))
            return
        if entry is not None:
            if entry.server_id is None:
                AppRepository.set_save_game_server_id(entry.id, res["server_id"])
            AppRepository.mark_save_game_synced(entry.id, res["version_id"],
                                                res["fingerprint"], res["slot"])
        self.refresh()
        QMessageBox.information(self, "上传成功", f"已写入存档位 {res['slot']}。")

    def _download_latest(self, entry=None):
        entry = entry or self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        slots = self._game_slots(entry.server_id)
        if not slots:
            QMessageBox.information(self, "提示", "云端暂无存档。")
            return
        dlg = SlotPickerDialog(self, slots, mode="download")
        if dlg.exec() != QDialog.Accepted:
            return
        info = dlg.selected_info() or {}
        if not info.get("versionId"):
            QMessageBox.information(self, "提示", "该存档位为空。")
            return
        self._download_slot(entry, dlg.selected_slot(), info.get("versionId"))

    def _download_slot(self, entry, slot, version_id):
        self._busy(True, "正在下载...")
        self._pending_download = (entry, slot, version_id)
        self._run_worker(
            ss.prepare_download, self._on_download_done,
            self._token, entry.server_id, version_id, entry.local_path)

    def _on_download_done(self, ok, res):
        self._busy(False)
        if not ok:
            if (res == ss.TAKEN_OVER and getattr(self, "_pending_download", None)
                    and self._confirm_take_over()):
                self._download_slot(*self._pending_download)
                return
            QMessageBox.warning(self, "下载失败", ss_http_msg(res))
            return
        tmp = res
        entry, slot, version_id = self._pending_download
        reply = QMessageBox.question(
            self, "确认覆盖",
            f"已下载并校验完成。\n是否用云端「存档位 {slot}」覆盖本地存档？\n"
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
        AppRepository.mark_save_game_synced(entry.id, version_id,
                                            ss.tree_fingerprint(entry.local_path), slot)
        msg = f"已覆盖为存档位 {slot} 的存档。"
        if backup:
            msg += f"\n原存档已备份到：{backup}"
        QMessageBox.information(self, "完成", msg)
        self.refresh()

    def _view_cloud(self):
        entry = self._selected_entry()
        if entry is None or entry.server_id is None:
            return
        slots = self._game_slots(entry.server_id)
        if not slots:
            QMessageBox.information(self, "提示", "云端暂无存档。")
            return
        dlg = SlotPickerDialog(self, slots, mode="view")
        if dlg.exec() != QDialog.Accepted:
            return
        info = dlg.selected_info() or {}
        if not info.get("versionId"):
            QMessageBox.information(self, "提示", "该存档位为空。")
            return
        SlotFilesDialog(self, self._token, entry.server_id,
                        info.get("versionId"), dlg.selected_slot()).exec()

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
        if QMessageBox.question(self, "删除本地条目",
                                "确定删除该本地条目？\n（不会删除磁盘上的存档目录，也不影响云端存档）",
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
