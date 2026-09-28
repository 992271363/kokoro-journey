"""主表格的列定义（唯一事实来源）。

列永远用**稳定 ID**定位，不用列号；列的显隐、顺序、排序键都以 ID 记录。
本模块是纯数据 + 纯函数，不依赖 Qt，方便单测与迁移。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ColumnSpec:
    id: str
    title: str
    # status/icon/text/number/time/percent/bool/placeholder
    kind: str
    sortable: bool = True
    default_visible: bool = False
    width: int = 90
    resize: str = "contents"        # contents | interactive | fixed
    reserved: bool = False          # 仅预留：本轮只作为属性/列位
    header: Optional[str] = None    # 表头显示文字；None 表示用 title

    def header_text(self) -> str:
        return self.title if self.header is None else self.header


COLUMN_LIST: List[ColumnSpec] = [
    ColumnSpec("status", "状态", "status", default_visible=True, width=46,
               resize="fixed", header=""),
    ColumnSpec("icon", "图标", "icon", sortable=False, default_visible=True,
               width=34, resize="fixed", header=""),
    ColumnSpec("name", "名称", "text", default_visible=True, width=200,
               resize="interactive"),
    ColumnSpec("session_focus", "本次焦点", "number", default_visible=True, width=90),
    ColumnSpec("session_lifetime", "本次运行", "number", default_visible=True, width=90),
    ColumnSpec("last_started_at", "最后启动", "time", default_visible=True, width=140),
    ColumnSpec("first_seen_at", "首次启动", "time", default_visible=True, width=140),
    ColumnSpec("total_focus", "总焦点时长", "number", default_visible=True, width=100),
    ColumnSpec("total_lifetime", "总运行时长", "number", default_visible=True, width=100),
    ColumnSpec("exe_name", "EXE 名称", "text", width=140),
    ColumnSpec("exe_path", "追踪进程路径", "text", width=260),
    ColumnSpec("launch_path", "启动路径", "text", width=260),
    ColumnSpec("launch_with_le", "用 Locale Emulator", "bool", width=110),
    ColumnSpec("focus_ratio", "焦点占比", "percent", width=90),
    ColumnSpec("is_watched", "是否监视", "bool", width=80),
    ColumnSpec("groups", "分组", "text", width=120),
    ColumnSpec("last_ended_at", "最后结束", "time", width=140),
    # 仅预留：本轮只登记为属性/列位，不建库字段、不做详情页控件
    ColumnSpec("completion_status", "通关状态", "placeholder", width=100, reserved=True),
    ColumnSpec("developer", "开发商", "placeholder", width=120, reserved=True),
    ColumnSpec("release_date", "发售日", "placeholder", width=110, reserved=True),
    ColumnSpec("rating", "评分", "placeholder", width=90, reserved=True),
]

COLUMNS: Dict[str, ColumnSpec] = {c.id: c for c in COLUMN_LIST}
DEFAULT_ORDER: List[str] = [c.id for c in COLUMN_LIST]
DEFAULT_VISIBLE: List[str] = [c.id for c in COLUMN_LIST if c.default_visible]

# 旧实现按列号存储（0..8）→ 稳定 ID
LEGACY_INDEX_TO_ID = {
    0: "status",
    1: "icon",
    2: "name",
    3: "session_focus",
    4: "session_lifetime",
    5: "last_started_at",
    6: "first_seen_at",
    7: "total_focus",
    8: "total_lifetime",
}

SETTING_ORDER = "tableColumnsOrder"
SETTING_VISIBLE = "tableColumnsVisible"
SETTING_SORT_ID = "tableSortId"
SETTING_SORT_ORDER = "tableSortOrder"
SETTING_MIGRATED = "tableColumnsMigrated"


def is_known(cid: str) -> bool:
    return cid in COLUMNS


def sanitize_order(order: Optional[Iterable[str]]) -> List[str]:
    """过滤未知 ID、去重，并把缺失的列按默认顺序补到末尾。"""
    result: List[str] = []
    for cid in order or []:
        if is_known(cid) and cid not in result:
            result.append(cid)
    for cid in DEFAULT_ORDER:
        if cid not in result:
            result.append(cid)
    return result


def sanitize_visible(visible: Optional[Iterable[str]], order: List[str]) -> List[str]:
    """仅保留已知且出现在 order 里的 ID；为空则回退默认可见集合。"""
    result = [cid for cid in (visible or []) if is_known(cid) and cid in order]
    if not result:
        return [cid for cid in DEFAULT_VISIBLE if cid in order]
    # 按 order 排序，保证“可见集合”的顺序语义与 order 一致
    return [cid for cid in order if cid in result]


def load_order(settings) -> List[str]:
    return sanitize_order(settings.get(SETTING_ORDER) if settings else None)


def load_visible(settings, order: List[str]) -> List[str]:
    return sanitize_visible(settings.get(SETTING_VISIBLE) if settings else None, order)


def migrate_legacy_prefs(settings) -> None:
    """把旧的“按列号”偏好一次性迁移成 ID 键（只做一次）。"""
    if settings is None or settings.get(SETTING_MIGRATED):
        return

    legacy_order = settings.get("tableColumnOrder")
    if isinstance(legacy_order, list) and legacy_order and not settings.get(SETTING_ORDER):
        ids = [LEGACY_INDEX_TO_ID[i] for i in legacy_order
               if isinstance(i, int) and i in LEGACY_INDEX_TO_ID]
        if ids:
            settings.set(SETTING_ORDER, sanitize_order(ids))

    legacy_sort_col = settings.get("tableSortColumn")
    if legacy_sort_col is not None and not settings.get(SETTING_SORT_ID):
        try:
            cid = LEGACY_INDEX_TO_ID.get(int(legacy_sort_col))
        except (TypeError, ValueError):
            cid = None
        if cid:
            settings.set(SETTING_SORT_ID, cid)
            legacy_sort_order = settings.get("tableSortOrder")
            if legacy_sort_order in ("asc", "desc"):
                settings.set(SETTING_SORT_ORDER, legacy_sort_order)

    settings.set(SETTING_MIGRATED, True)


# ---------------- 展示与搜索（纯函数，表格与搜索共用） ----------------

def _stem(name: Optional[str]) -> str:
    return os.path.splitext(os.path.basename(name or ""))[0]


def display_name(app) -> str:
    """列表显示名：有自定义名用自定义名，否则回退 EXE 名。"""
    custom = (getattr(app, "custom_name", None) or "").strip()
    return custom or _stem(getattr(app, "exe_name", ""))


def search_texts(app) -> List[str]:
    """搜索用文本：覆盖所有属性的数据（与列显隐无关）。"""
    values = [
        display_name(app),
        getattr(app, "custom_name", "") or "",
        getattr(app, "exe_name", "") or "",
        getattr(app, "exe_path", "") or "",
        getattr(app, "launch_path", "") or "",
        getattr(app, "last_start_at", "") or "",
        getattr(app, "first_seen_at", "") or "",
        getattr(app, "last_ended_at", "") or "",
        "用 Locale Emulator" if getattr(app, "launch_with_le", False) else "",
        "是否监视" if getattr(app, "is_watched", True) else "",
    ]
    return [v for v in values if v]
