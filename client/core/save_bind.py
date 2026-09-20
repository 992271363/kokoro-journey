"""换机/重装闭环逻辑（不含 UI）。

- classify_cloud_binding：判断某云端游戏与本地条目的关系
- cloud_game_state：判断关联条目的云端状态（已删除 / 暂无版本 / 正常）
- download_cloud_game_to：选云端游戏 -> 下最新版本 -> 应用到本地目录 -> 创建/关联本地条目

不涉及去重/悬浮窗/差异查看；不改动 P1/P2/P3 行为。
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from db.repository import AppRepository
from core import save_sync as ss

# 关联关系
BOUND_SAME = "bound_same"      # 本地已有条目关联到该云端游戏
NEW = "new"                    # 本地没有该游戏
NAME_UNBOUND = "name_unbound"  # 本地有同名但未关联
NAME_OTHER = "name_other"      # 本地有同名但关联到别的云端游戏（异常）

# 云端状态
STATE_OK = "ok"
STATE_DELETED = "deleted"        # 云端游戏已删除
STATE_NO_VERSION = "no_version"  # 游戏在，但暂无版本


def classify_cloud_binding(entries, cloud_game) -> str:
    gid = cloud_game.get("id")
    name = cloud_game.get("name")
    for e in entries:
        if e.server_id is not None and e.server_id == gid:
            return BOUND_SAME
    for e in entries:
        if e.name == name:
            return NAME_UNBOUND if e.server_id is None else NAME_OTHER
    return NEW


def cloud_game_state(local_entry, cloud_map) -> str:
    if local_entry.server_id is None:
        return STATE_OK
    cloud = cloud_map.get(local_entry.server_id)
    if cloud is None:
        return STATE_DELETED
    if not cloud.get("latestVersion"):
        return STATE_NO_VERSION
    return STATE_OK


def _same_path(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def download_cloud_game_to(token: str, cloud_game: dict, local_path: str, entries,
                           bind_entry_id: Optional[int] = None,
                           slot: Optional[int] = None, version_id: Optional[int] = None,
                           progress_cb=None) -> Tuple[bool, object]:
    """把云端「指定存档位(slot)的版本」下载到 local_path，并创建/关联本地条目。

    返回 (True, {"local_id","server_id","slot","version_id","fingerprint","backup"})
    或 (False, 错误)。
    """
    if not local_path:
        return False, "未指定本地目录"
    if not cloud_game or not cloud_game.get("id"):
        return False, "云端游戏无效"
    if version_id is None:
        return False, "云端该存档位暂无版本"

    server_id = cloud_game["id"]

    # 目录占用检查（跳过本游戏自身已关联的条目 / 正在关联的条目）
    for e in entries:
        if e.server_id == server_id or (bind_entry_id is not None and e.id == bind_entry_id):
            continue
        if _same_path(e.local_path, local_path):
            return False, "该目录已被其它存档条目占用"

    ok, tmp = ss.prepare_download(token, server_id, version_id, local_path,
                                  progress_cb=progress_cb)
    if not ok:
        return False, tmp

    # 空目录前置：目标存在且为空时先移除，避免产生空的 .bak
    try:
        if os.path.isdir(local_path) and not os.listdir(local_path):
            os.rmdir(local_path)
    except OSError:
        pass

    ok2, backup = ss.apply_download(tmp, local_path)
    if not ok2:
        ss.discard_download(tmp)
        return False, backup

    fingerprint = ss.tree_fingerprint(local_path)

    if bind_entry_id is not None:
        if not AppRepository.bind_save_game_to_server(bind_entry_id, server_id,
                                                      version_id, fingerprint, slot):
            return False, "关联本地条目失败"
        local_id = bind_entry_id
    else:
        bound = next((e for e in entries if e.server_id == server_id), None)
        if bound is not None:
            AppRepository.mark_save_game_synced(bound.id, version_id, fingerprint, slot)
            local_id = bound.id
        else:
            obj = AppRepository.create_bound_save_game(
                cloud_game.get("name") or "未命名", local_path, server_id,
                version_id, fingerprint, slot)
            if obj is None:
                return False, "创建本地条目失败"
            local_id = obj.id

    return True, {"local_id": local_id, "server_id": server_id, "slot": slot,
                  "version_id": version_id, "fingerprint": fingerprint, "backup": backup}
