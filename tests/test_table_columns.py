"""列系统：稳定 ID / 偏好迁移 / 按 ID 更新 / 名称回退 / 搜索范围 / 导出导入兼容。"""
import _common  # noqa: F401

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget

from db import io
from db.repository import AppInfo, AppRepository
from ui import table_columns as tc
from ui.table import AppTableManager
from ui.table_columns_dialog import ChooseColumnsDialog
from util.config import Settings

_common.ensure_db()

app = QApplication(sys.argv)
settings = Settings()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def reset_column_prefs():
    for key in (tc.SETTING_ORDER, tc.SETTING_VISIBLE, tc.SETTING_SORT_ID,
                tc.SETTING_SORT_ORDER, tc.SETTING_MIGRATED):
        settings.set(key, None)
    settings.set(tc.SETTING_ORDER, list(tc.DEFAULT_ORDER))
    settings.set(tc.SETTING_VISIBLE, list(tc.DEFAULT_VISIBLE))
    settings.set(tc.SETTING_MIGRATED, True)


def make_app(name: str, focus: int = 0, life: int = 0, custom=None) -> AppInfo:
    return AppInfo(
        exe_path=rf"c:\le\col\{name}.exe",
        launch_path=rf"c:\le\col\{name}.exe",
        exe_name=f"{name}.exe",
        total_focus_seconds=focus,
        total_lifetime_seconds=life,
        last_start_at="",
        first_seen_at="",
        custom_name=custom,
    )


def new_manager() -> AppTableManager:
    reset_column_prefs()
    return AppTableManager(QTableWidget(), None, settings)


# ---------------- 列定义 ----------------
ids = [c.id for c in tc.COLUMN_LIST]
check("列 ID 唯一", len(ids) == len(set(ids)))
check("默认可见 = 原来的 9 列",
      tc.DEFAULT_VISIBLE == ["status", "icon", "name", "session_focus",
                             "session_lifetime", "last_started_at", "first_seen_at",
                             "total_focus", "total_lifetime"])
check("旧列号映射（2 → name、7 → total_focus）",
      tc.LEGACY_INDEX_TO_ID[2] == "name" and tc.LEGACY_INDEX_TO_ID[7] == "total_focus")
check("预留列已登记且默认隐藏",
      all(tc.COLUMNS[c].reserved for c in ("completion_status", "developer",
                                           "release_date", "rating"))
      and not any(c in tc.DEFAULT_VISIBLE for c in
                  ("completion_status", "developer", "release_date", "rating")))
check("状态/图标表头留空", tc.COLUMNS["status"].header_text() == ""
      and tc.COLUMNS["icon"].header_text() == "")
check("exe_name 默认隐藏、name 默认显示",
      "exe_name" not in tc.DEFAULT_VISIBLE and "name" in tc.DEFAULT_VISIBLE)

_san = tc.sanitize_order(["name", "name", "不存在"])
check("sanitize_order 去重/过滤/补全",
      _san[0] == "name" and len(_san) == len(tc.DEFAULT_ORDER)
      and len(set(_san)) == len(tc.DEFAULT_ORDER) and "不存在" not in _san)
check("sanitize_visible 空 → 回退默认",
      tc.sanitize_visible([], tc.DEFAULT_ORDER) == tc.DEFAULT_VISIBLE)

# ---------------- 旧偏好一次性迁移 ----------------
reset_column_prefs()
settings.set(tc.SETTING_ORDER, None)
settings.set(tc.SETTING_VISIBLE, None)
settings.set(tc.SETTING_SORT_ID, None)
settings.set(tc.SETTING_MIGRATED, None)
settings.set("tableColumnOrder", [2, 0, 1])
settings.set("tableSortColumn", 7)
settings.set("tableSortOrder", "desc")
tc.migrate_legacy_prefs(settings)
check("迁移：列顺序 → ID",
      settings.get(tc.SETTING_ORDER)[:3] == ["name", "status", "icon"])
check("迁移：排序键 → ID",
      settings.get(tc.SETTING_SORT_ID) == "total_focus"
      and settings.get(tc.SETTING_SORT_ORDER) == "desc")
check("迁移标记置位", settings.get(tc.SETTING_MIGRATED) is True)
settings.set("tableSortColumn", 3)
tc.migrate_legacy_prefs(settings)
check("迁移只做一次（旧键不再影响）", settings.get(tc.SETTING_SORT_ID) == "total_focus")

# ---------------- 管理器：按 ID 渲染 / 更新 ----------------
manager = new_manager()
a = make_app("alpha", focus=100, life=200)
b = make_app("beta", focus=50, life=80)
manager.refresh([a, b])

check("按 ID 取列号", manager.col_index("name") >= 0
      and manager.col_index("exe_name") == -1)   # exe_name 默认隐藏

manager.set_column_visible("icon", False)
check("隐藏图标列后名称列左移",
      manager.col_index("name") == 1 and manager.table.columnCount() == 8)
check("表格标题与可见 ID 一致",
      [manager.table.horizontalHeaderItem(c).text() for c in range(manager.table.columnCount())]
      == [tc.COLUMNS[c].header_text() for c in manager.visible_ids])

# 模拟一次实时刷新（按 ID 写入）
manager.update_status({a.exe_path: {"focus": 10, "runtime_seconds": 20, "is_focused": True}})
fc = manager.col_index("session_focus")
tf = manager.col_index("total_focus")
check("实时更新写入本次焦点", manager.table.item(0, fc) is not None
      and manager.table.item(0, fc).data(Qt.UserRole) == 10)
check("总量 = 基准 + 本次", manager.table.item(0, tf).data(Qt.UserRole) == 110)

# 隐藏总量列再显示：基准不丢
manager.set_column_visible("total_focus", False)
manager.update_status({a.exe_path: {"focus": 30, "runtime_seconds": 60, "is_focused": False}})
manager.set_column_visible("total_focus", True)
tf = manager.col_index("total_focus")
check("隐藏再显示后总量不丢", manager.table.item(0, tf).data(Qt.UserRole) == 130)

# 隐藏当前排序列 → 清除排序
manager.sort_by_id("total_focus", Qt.AscendingOrder)
check("排序按 ID 记录", settings.get(tc.SETTING_SORT_ID) == "total_focus")
manager.set_column_visible("total_focus", False)
check("隐藏排序列后清除排序", settings.get(tc.SETTING_SORT_ID) is None)

# ---------------- 排序后行身份不错位（回归） ----------------
manager3 = new_manager()
low = make_app("low", focus=10, life=10)
mid = make_app("mid", focus=50, life=50)
high = make_app("high", focus=100, life=100)
manager3.refresh([low, mid, high])
manager3.sort_by_id("total_focus", Qt.DescendingOrder)
visual = [manager3.exe_path_at_row(r) for r in range(manager3.table.rowCount())]
check("降序后视觉顺序反转",
      visual == [high.exe_path, mid.exe_path, low.exe_path])
check("排序后按行取 exe_path 正确",
      manager3._get_exe_path_by_row(0) == high.exe_path
      and manager3._get_exe_path_by_row(2) == low.exe_path)

# 焦点最小的应用（降序后排最后一行）处于运行/聚焦状态
manager3.update_status({low.exe_path: {"focus": 7, "runtime_seconds": 9,
                                       "is_focused": True}})
low_row = next(r for r in range(manager3.table.rowCount())
               if manager3.exe_path_at_row(r) == low.exe_path)
sc = manager3.col_index("status")
fc = manager3.col_index("session_focus")
tf = manager3.col_index("total_focus")
check("运行时状态落在正确行",
      low_row == 2
      and manager3.table.item(low_row, sc).data(Qt.UserRole) == 2)
check("其它行不被误点亮",
      all(manager3.table.item(r, sc).data(Qt.UserRole) <= 0
          for r in range(manager3.table.rowCount()) if r != low_row))
check("正确行写入本次焦点与总量",
      manager3.table.item(low_row, fc).data(Qt.UserRole) == 7
      and manager3.table.item(low_row, tf).data(Qt.UserRole) == 17)

# ---------------- 列序稳定性 / 排序状态收敛 ----------------
manager4 = new_manager()
manager4.set_column_visible("exe_path", True)
manager4.set_column_visible("exe_name", True)   # order 里 exe_name 在 exe_path 之前
check("新显示列按 order 位置插入",
      manager4.visible_ids == [c for c in manager4.order_ids if c in manager4.visible_ids])
check("列序重启后稳定（sanitize 往返不变）",
      tc.sanitize_visible(manager4.visible_ids, manager4.order_ids) == manager4.visible_ids)

_manager5 = new_manager()
_manager5.refresh([make_app("x", focus=10), make_app("y", focus=20)])
_manager5.sort_by_id("total_focus", Qt.DescendingOrder)
_manager5.set_column_visible("icon", False)
check("改列后排序保持开启", _manager5.table.isSortingEnabled())
check("改列后仍记录按 ID 排序", settings.get(tc.SETTING_SORT_ID) == "total_focus")
_manager5.set_column_visible("total_focus", False)
check("隐藏排序列后指示器已清除",
      _manager5.table.horizontalHeader().sortIndicatorSection() == -1)
check("隐藏排序列后排序仍开启（可点表头）", _manager5.table.isSortingEnabled())

# ---------------- 排序后缩放/重绘不丢单元格（回归） ----------------
manager6 = new_manager()
m_apps = [make_app("p1", focus=10, life=10),
          make_app("p2", focus=50, life=50),
          make_app("p3", focus=90, life=90)]
manager6.refresh(m_apps)
manager6.sort_by_id("total_focus", Qt.DescendingOrder)
_zoom_base = sum(int(a.total_focus_seconds or 0) for a in m_apps)
check("缩放前排序开启", manager6.table.isSortingEnabled())


def _holes(manager) -> int:
    return sum(1 for r in range(manager.table.rowCount())
               if any(manager.table.item(r, c) is None
                      for c in range(manager.table.columnCount())))


manager6.apply_zoom(2.0)
fc6 = manager6.col_index("total_focus")
check("排序后缩放不丢单元格", _holes(manager6) == 0)
check("排序后缩放行数不变", manager6.table.rowCount() == 3)
check("排序后缩放合计不变",
      sum(int(manager6.table.item(r, fc6).data(Qt.UserRole) or 0)
          for r in range(manager6.table.rowCount())) == _zoom_base)
check("排序后缩放排序仍开启", manager6.table.isSortingEnabled())

manager6._render_rows()
check("直接重绘不丢单元格", _holes(manager6) == 0)

# ---------------- 名称回退 ----------------
manager2 = new_manager()
plain = make_app("plain", custom=None)
named = make_app("raw", custom="老头环")
manager2.refresh([plain, named])
nc = manager2.col_index("name")
check("未设置自定义名 → 回退 EXE 名", manager2.table.item(0, nc).text() == "plain")
check("有自定义名 → 显示自定义名", manager2.table.item(1, nc).text() == "老头环")
check("AppInfo.display_name 口径", plain.display_name == "plain"
      and named.display_name == "老头环")

# 名称排序：按“显示名”，不是 EXE 名（自定义名生效）
manager2b = new_manager()
p_app = make_app("zzz", custom="aaa")
q_app = make_app("aaa", custom="zzz")
manager2b.refresh([p_app, q_app])
manager2b.sort_by_id("name", Qt.AscendingOrder)
nc2 = manager2b.col_index("name")
check("名称排序按显示名而非 EXE 名",
      manager2b.table.item(0, nc2).text().startswith("aaa")
      and manager2b.exe_path_at_row(0) == p_app.exe_path)

# ---------------- 搜索覆盖隐藏列 ----------------
check("搜索文本包含隐藏列数据（exe_path）",
      any("col" in v for v in tc.search_texts(plain)))

# ---------------- repository：改名与路径变化 ----------------
AppRepository.add_app(r"c:\le\repo\demo.exe", "demo.exe")
check("改名写自定义名", AppRepository.rename_app(r"c:\le\repo\demo.exe", "演示"))
check("自定义名已保存", AppRepository.get_app_by_path(r"c:\le\repo\demo.exe").custom_name == "演示")
AppRepository.change_tracking_path(r"c:\le\repo\demo.exe", r"c:\le\repo\renamed.exe")
moved = AppRepository.get_app_by_path(r"c:\le\repo\renamed.exe")
check("改路径刷新 EXE 名", moved is not None and moved.executable_name == "renamed")
check("改路径不覆盖自定义名", moved.custom_name == "演示")

# ---------------- 导出 / 导入兼容 ----------------
out = _common.tmpdir("kokoro_cols_") + os.sep + "export.json"
ok_export, _ = io.export_data(out, "json")
check("导出成功", ok_export)
with open(out, encoding="utf-8") as f:
    data = json.load(f)
entry = next((x for x in data["applications"] if x["executable_path"] == r"c:\le\repo\renamed.exe"), None)
check("导出含 exe_name / custom_name",
      entry is not None and entry.get("exe_name") == "renamed"
      and entry.get("custom_name") == "演示" and entry.get("name") == "演示")

# 旧格式文件（只有 name）→ 导入为自定义名
legacy = _common.tmpdir("kokoro_cols_legacy_") + os.sep + "legacy.json"
with open(legacy, "w", encoding="utf-8") as f:
    json.dump({"applications": [{
        "name": "旧名字",
        "executable_path": r"c:\le\repo\legacy.exe",
        "launch_path": r"c:\le\repo\legacy.exe",
        "is_watched": True,
    }]}, f, ensure_ascii=False)
ok_import, _ = io.import_data(legacy)
check("旧文件导入成功", ok_import)
legacy_app = AppRepository.get_app_by_path(r"c:\le\repo\legacy.exe")
check("旧文件 name → 自定义名",
      legacy_app is not None and legacy_app.custom_name == "旧名字")

# ---------------- 选择列弹窗（不弹窗，直接验证逻辑） ----------------
dlg = ChooseColumnsDialog(None, tc.DEFAULT_ORDER, tc.DEFAULT_VISIBLE)
check("弹窗列出全部列", dlg.list.count() == len(tc.DEFAULT_ORDER))
before = dlg.result_state()
check("确定前状态 = 传入状态", before[1] == tc.DEFAULT_VISIBLE)
dlg._reset()
check("恢复默认", dlg.result_state()[1] == tc.DEFAULT_VISIBLE)
dlg.close()

AppRepository.delete_app_completely(r"c:\le\repo\renamed.exe")
AppRepository.delete_app_completely(r"c:\le\repo\legacy.exe")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
