"""云存档自动化：登录时同步策略 + 关联进程匹配。

策略（非破坏性）：
- 本地有改动、云端未变   -> 上传（服务端保留历史版本）
- 云端更新、本地未改动   -> 下载并应用（本地无改动可安全覆盖）
- 本地与云端都变化       -> 冲突，跳过，交由用户手动选择
- 从未上传（无 server_id）-> 登录同步不处理，需用户手动上传
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


def entry_status(entry, cloud_game) -> Tuple[str, Optional[int]]:
    try:
        if entry.local_path and os.path.isdir(entry.local_path):
            local_changed = ss.tree_fingerprint(entry.local_path) != entry.local_fingerprint
        else:
            local_changed = True
    except Exception:
        local_changed = True
    latest = cloud_game.get("latestVersion") if cloud_game else None
    cloud_newer = bool(latest) and (
        entry.last_synced_version is None or latest > entry.last_synced_version
    )
    status = ss.sync_status(local_changed, cloud_newer, entry.last_synced_version is not None)
    return status, latest


def sync_entry_on_login(token: str, entry, cloud_game) -> Tuple[bool, str]:
    if entry.server_id is None:
        return True, "未关联云端，跳过"

    status, latest = entry_status(entry, cloud_game)

    if status in (ss.STATUS_IN_SYNC, ss.STATUS_NOT_SYNCED):
        return True, "无需处理"

    if status == ss.STATUS_LOCAL:
        ok, res = ss.upload_game(token, entry.local_path, entry.name, entry.server_id)
        if not ok:
            return False, res
        AppRepository.mark_save_game_synced(entry.id, res["version"], res["fingerprint"])
        return True, f"已上传 v{res['version']}"

    if status == ss.STATUS_CLOUD:
        # 优先用 list_games 已带回的最新版本 id，省掉一次 list_versions 请求
        target_id = cloud_game.get("latestVersionId") if cloud_game else None
        if target_id is None or (cloud_game.get("latestVersion") != latest):
            ok, versions = ss.list_versions(token, entry.server_id)
            if not ok:
                return False, versions
            target = next((v for v in versions if v["versionNumber"] == latest), None)
            if target is None:
                return False, "未找到云端版本"
            target_id = target["id"]
        ok, tmp = ss.prepare_download(token, entry.server_id, target_id, entry.local_path)
        if not ok:
            return False, tmp
        ok2, backup = ss.apply_download(tmp, entry.local_path)
        if not ok2:
            ss.discard_download(tmp)
            return False, backup
        AppRepository.mark_save_game_synced(entry.id, latest,
                                            ss.tree_fingerprint(entry.local_path))
        return True, f"已下载 v{latest}"

    return True, "冲突，已跳过"


def auto_sync_all_on_login(token: str, progress_cb=None) -> Tuple[bool, str]:
    ok, res = ss.claim_device(token)
    if not ok:
        return False, _msg(res)
    ok, games = ss.list_games(token)
    if not ok:
        return False, _msg(res)
    cloud_map = {g["id"]: g for g in games}
    entries = AppRepository.get_all_save_games()
    done = skipped = failed = 0
    for i, entry in enumerate(entries, 1):
        if entry.server_id is None:
            skipped += 1
            continue
        ok2, msg = sync_entry_on_login(token, entry, cloud_map.get(entry.server_id))
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
    """自动上传单个条目：先登记设备（单设备接管），再上传。

    返回 (True, {"server_id","version","fingerprint"}) 或 (False, 错误)。
    """
    ok, res = ss.claim_device(token)
    if not ok:
        return False, _msg(res)
    ok, res = ss.upload_game(token, entry.local_path, entry.name, entry.server_id)
    if not ok:
        return False, _msg(res)
    return True, res
