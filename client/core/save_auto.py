"""云存档自动化：登录时同步策略 + 关联进程匹配（存档位模型）。

策略（非破坏性）：
- 本地有改动、绑定槽位未变 -> 上传（自动选槽：最小空槽，否则覆盖最旧日期槽）
- 绑定槽位已更新、本地未改 -> 下载并应用（本地无改动可安全覆盖）
- 本地与槽位都变化         -> 冲突，跳过，交由用户手动选择
- 从未上传（无 server_id） -> 登录同步不处理，需用户手动上传

约定：`SaveGame.last_synced_version` 存的是该槽位内容对应的**服务端版本 id**；
`SaveGame.server_slot` 记录上次同步使用的存档位。
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from db.repository import AppRepository
from core import save_sync as ss
from util.path import normalize_exe_path


def _norm_name(name: str) -> str:
    return os.path.splitext(os.path.basename(name or ""))[0].lower()


def match_save_games_for_exe(exe_name: str) -> List:
    """返回关联了该 EXE 名称的本地存档条目。"""
    target = _norm_name(exe_name)
    if not target:
        return []
    apps = {normalize_exe_path(a.exe_path): a.exe_name for a in AppRepository.get_all_apps()}
    result = []
    for g in AppRepository.get_all_save_games():
        if not g.linked_app_path:
            continue
        app_name = apps.get(normalize_exe_path(g.linked_app_path))
        if app_name and _norm_name(app_name) == target:
            result.append(g)
    return result


def entry_status(entry, slot_info) -> Tuple[str, Optional[int]]:
    """状态与「条目绑定的存档位」比较；返回 (status, 该槽 versionId|None)。"""
    try:
        if entry.local_path and os.path.isdir(entry.local_path):
            local_changed = ss.tree_fingerprint(entry.local_path) != entry.local_fingerprint
        else:
            local_changed = True
    except Exception:
        local_changed = True
    cloud_version_id = slot_info.get("versionId") if slot_info else None
    cloud_newer = cloud_version_id is not None and cloud_version_id != entry.last_synced_version
    status = ss.sync_status(local_changed, cloud_newer,
                            entry.last_synced_version is not None)
    return status, cloud_version_id


def _slots_of(token: str, server_id: Optional[int]):
    if server_id is None:
        return True, []
    return ss.list_slots(token, server_id)


def sync_entry_on_login(token: str, entry) -> Tuple[bool, str]:
    if entry.server_id is None:
        return True, "未关联云端，跳过"

    ok, slots = _slots_of(token, entry.server_id)
    if not ok:
        return False, slots
    slot_info = next((s for s in slots if s.get("slot") == entry.server_slot), None)
    status, cloud_vid = entry_status(entry, slot_info)

    if status in (ss.STATUS_IN_SYNC, ss.STATUS_NOT_SYNCED):
        return True, "无需处理"

    if status == ss.STATUS_LOCAL:
        slot = ss.pick_auto_slot(slots)
        identifier = getattr(entry, "identifier", None) or entry.name
        ok, res = ss.upload_game(token, entry.local_path, entry.name, identifier,
                                 server_id=entry.server_id, slot=slot)
        if not ok:
            return False, res
        AppRepository.mark_save_game_synced(entry.id, res["version_id"],
                                            res["fingerprint"], slot)
        return True, f"已上传（存档位 {slot}）"

    if status == ss.STATUS_CLOUD:
        ok, tmp = ss.prepare_download(token, entry.server_id, cloud_vid, entry.local_path)
        if not ok:
            return False, tmp
        ok2, backup = ss.apply_download(tmp, entry.local_path)
        if not ok2:
            ss.discard_download(tmp)
            return False, backup
        AppRepository.mark_save_game_synced(entry.id, cloud_vid,
                                            ss.tree_fingerprint(entry.local_path),
                                            entry.server_slot)
        return True, f"已下载（存档位 {entry.server_slot}）"

    return True, "冲突，已跳过"


def auto_sync_all_on_login(token: str, progress_cb=None) -> Tuple[bool, str]:
    ok, res = ss.claim_device(token)
    if not ok:
        return False, _msg(res)
    entries = AppRepository.get_all_save_games()
    done = skipped = failed = 0
    for i, entry in enumerate(entries, 1):
        if entry.server_id is None:
            skipped += 1
            continue
        ok2, msg = sync_entry_on_login(token, entry)
        if not ok2:
            if msg == ss.TAKEN_OVER:
                return False, "云同步已由其他设备接管"
            failed += 1
        elif isinstance(msg, str) and msg.startswith("冲突"):
            skipped += 1
        else:
            done += 1
        if progress_cb:
            progress_cb(i, len(entries), "登录同步")
    return True, f"登录同步完成：处理 {done}，跳过 {skipped}，失败 {failed}"


def _msg(res) -> str:
    return "云同步已由其他设备接管" if res == ss.TAKEN_OVER else str(res)


def upload_entry(token: str, entry) -> Tuple[bool, object]:
    """自动上传单个条目：登记设备 -> 自动选槽 -> 上传（覆盖同槽）。

    返回 (True, {"server_id","slot","version_id","version","fingerprint"}) 或 (False, 错误)。
    """
    ok, res = ss.claim_device(token)
    if not ok:
        return False, _msg(res)

    # 未关联时先按标识符找已存在的远端游戏，避免盲目写入槽位 1 覆盖已有存档。
    identifier = getattr(entry, "identifier", None) or entry.name
    server_id = entry.server_id
    if server_id is None:
        server_id = ss._find_remote_game_id(token, identifier)

    slot = 1
    if server_id is not None:
        ok, slots = _slots_of(token, server_id)
        if not ok:
            return False, _msg(slots)
        picked = ss.pick_auto_slot(slots)
        if picked is not None:
            slot = picked

    ok, res = ss.upload_game(token, entry.local_path, entry.name, identifier,
                             server_id, slot=slot)
    if not ok:
        return False, _msg(res)
    return True, res
