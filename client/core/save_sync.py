"""云存档客户端逻辑：manifest / 指纹 / 状态判定 / API 调用 / 后台 worker。

- 纯函数（build_tree/fingerprint/validate/safe_join_local/sync_status）便于离线测试；
- API 调用返回 (ok, data_or_errormsg)；服务端 409 统一返回 "TAKEN_OVER"。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import time
from typing import List, Optional, Tuple

import requests
from PySide6.QtCore import QObject, Signal, Slot

from core.api import API_URL
from core.http_client import get_session
from util.device import get_device_id

TIMEOUT = 60
UPLOAD_TIMEOUT = 600

MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 90 * 1024 * 1024  # 客户端单文件硬拦截

RETRY_ATTEMPTS = 3
RETRY_BACKOFF = (1, 3, 9)  # 秒
_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

TAKEN_OVER = "TAKEN_OVER"

STATUS_IN_SYNC = "in_sync"
STATUS_LOCAL = "local_changed"
STATUS_CLOUD = "cloud_newer"
STATUS_CONFLICT = "conflict"
STATUS_NOT_SYNCED = "not_synced"


# ---------------- 纯函数（可离线测试） ----------------

def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


# 仅用于 build_manifest：按 (绝对路径, 大小, mtime_ns) 记忆哈希，避免重复读盘。
# 服务端仍会对收到的内容重算 sha256 校验，缓存不会削弱完整性检查。
_SHA256_CACHE: dict = {}


def _cached_sha256(path: str, size: int, mtime_ns: int) -> str:
    key = (os.path.abspath(path), int(size), int(mtime_ns))
    hit = _SHA256_CACHE.get(key)
    if hit is not None:
        return hit
    digest = sha256_file(path)
    _SHA256_CACHE[key] = digest
    return digest


def build_tree(local_dir: str) -> List[dict]:
    """扫描目录，得到 (相对路径, 大小, mtime_ns) 列表（不含内容哈希）。"""
    items: List[dict] = []
    for root, _dirs, files in os.walk(local_dir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, local_dir).replace(os.sep, "/")
            try:
                st = os.stat(full)
            except OSError:
                continue
            items.append({"path": rel, "size": st.st_size, "mtime_ns": st.st_mtime_ns})
    items.sort(key=lambda x: x["path"])
    return items


def timestamp_fingerprint(items: List[dict]) -> str:
    data = json.dumps([[m["path"], m["size"], m.get("mtime_ns")] for m in items],
                      ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def tree_fingerprint(local_dir: str) -> str:
    return timestamp_fingerprint(build_tree(local_dir))


def build_manifest(local_dir: str) -> List[dict]:
    """扫描目录，得到可上传清单（含 sha256）。

    sha256 按 (绝对路径, 大小, mtime_ns) 缓存，避免重复同步时全量重算；
    这与 timestamp_fingerprint 的判据一致，不改变清单内容与服务端校验。
    """
    items = build_tree(local_dir)
    for m in items:
        full = os.path.join(local_dir, m["path"])
        m["sha256"] = _cached_sha256(full, m["size"], m["mtime_ns"])
    return items


def validate_client_manifest(manifest: List[dict]) -> Tuple[bool, str]:
    if not manifest:
        return False, "目录为空"
    total = sum(int(m["size"]) for m in manifest)
    if total > MAX_TOTAL_BYTES:
        return False, "存档总大小超过 512MB"
    for m in manifest:
        if int(m["size"]) > MAX_FILE_BYTES:
            return False, f"单文件超过 90MB: {m['path']}"
    return True, ""


def safe_join_local(base: str, rel: str) -> str:
    rel = str(rel).replace("\\", "/")
    if rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"):
        raise ValueError("非法相对路径")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("路径穿越")
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, *parts))
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise ValueError("路径越界")
    return target


def sync_status(local_changed: bool, cloud_newer: bool, has_last_synced: bool) -> str:
    if not has_last_synced:
        return STATUS_NOT_SYNCED
    if local_changed and cloud_newer:
        return STATUS_CONFLICT
    if local_changed:
        return STATUS_LOCAL
    if cloud_newer:
        return STATUS_CLOUD
    return STATUS_IN_SYNC


# ---------------- HTTP ----------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Device-Id": get_device_id()}


def _detail(r: requests.Response) -> str:
    try:
        return r.json().get("detail") or f"HTTP {r.status_code}"
    except Exception:
        return f"HTTP {r.status_code}"


TAKEN_OVER_HEADER = "X-Cloud-Error"
TAKEN_OVER_HEADER_VALUE = "taken_over"
TAKEN_OVER_DETAIL = "云同步已由其他设备接管"


def _is_taken_over(r: requests.Response) -> bool:
    """409 不都是"被其他设备接管"（还有"同名游戏已存在"），据标识区分。"""
    if r.headers.get(TAKEN_OVER_HEADER) == TAKEN_OVER_HEADER_VALUE:
        return True
    return _detail(r) == TAKEN_OVER_DETAIL


def _detail_or_taken_over(r: requests.Response) -> str:
    return TAKEN_OVER if _is_taken_over(r) else _detail(r)


def _friendly_error(exc: Exception) -> str:
    """把底层网络异常翻译成用户能看懂的中文提示。"""
    if isinstance(exc, requests.exceptions.Timeout):
        return "请求超时，请检查网络后重试。"
    if isinstance(exc, requests.exceptions.SSLError):
        return "网络连接被中断（可能超时、文件过大或代理不稳定），请重试。"
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return "传输过程中断，请重试。"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "网络连接失败，请检查网络或代理设置后重试。"
    return f"网络错误：{exc}"


def _send(make_request):
    """带退避重试执行网络请求；可重试错误重试，其余立即抛出。"""
    last = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return make_request()
        except _NETWORK_ERRORS as e:
            last = e
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_BACKOFF[attempt])
    raise last


def _post_json(token: str, path: str, payload: Optional[dict] = None,
               timeout: int = TIMEOUT) -> Tuple[bool, object]:
    try:
        r = _send(lambda: get_session().post(f"{API_URL}/{path.lstrip('/')}", json=payload,
                                             headers=_headers(token), timeout=timeout))
    except requests.exceptions.RequestException as e:
        return False, _friendly_error(e)
    if r.status_code == 409:
        return False, _detail_or_taken_over(r)
    if r.status_code >= 400:
        return False, _detail(r)
    return True, r.json()


def _get_json(token: str, path: str, params: Optional[dict] = None,
              timeout: int = TIMEOUT) -> Tuple[bool, object]:
    try:
        r = _send(lambda: get_session().get(f"{API_URL}/{path.lstrip('/')}", params=params,
                                            headers=_headers(token), timeout=timeout))
    except requests.exceptions.RequestException as e:
        return False, _friendly_error(e)
    if r.status_code == 409:
        return False, _detail_or_taken_over(r)
    if r.status_code >= 400:
        return False, _detail(r)
    return True, r.json()


def _delete(token: str, path: str) -> Tuple[bool, object]:
    try:
        r = _send(lambda: get_session().delete(f"{API_URL}/{path.lstrip('/')}",
                                               headers=_headers(token), timeout=TIMEOUT))
    except requests.exceptions.RequestException as e:
        return False, _friendly_error(e)
    if r.status_code == 409:
        return False, _detail_or_taken_over(r)
    if r.status_code >= 400:
        return False, _detail(r)
    return True, r.json()


# ---------------- 业务接口 ----------------

def claim_device(token: str) -> Tuple[bool, object]:
    return _post_json(token, "/saves/device/claim", {})


def get_device(token: str) -> Tuple[bool, object]:
    return _get_json(token, "/saves/device")


def list_games(token: str) -> Tuple[bool, object]:
    return _get_json(token, "/saves/games")


def create_remote_game(token: str, name: str) -> Tuple[bool, object]:
    return _post_json(token, "/saves/games", {"name": name})


def _find_remote_game_id(token: str, name: str) -> Optional[int]:
    """按名字查已存在的远端游戏 id。

    上次上传半途失败时服务端可能已建好同名游戏（本地 server_id 仍为空），
    这里先复用，避免重试时再建同名被 409 拒绝。
    """
    ok, games = list_games(token)
    if not ok or not isinstance(games, list):
        return None
    return next((g["id"] for g in games if g.get("name") == name), None)


def delete_remote_game(token: str, server_id: int) -> Tuple[bool, object]:
    return _delete(token, f"/saves/games/{server_id}")


def list_versions(token: str, server_id: int) -> Tuple[bool, object]:
    return _get_json(token, f"/saves/games/{server_id}/versions")


def list_version_files(token: str, server_id: int, version_id: int) -> Tuple[bool, object]:
    return _get_json(token, f"/saves/games/{server_id}/versions/{version_id}/files")


def delete_version(token: str, server_id: int, version_id: int) -> Tuple[bool, object]:
    return _delete(token, f"/saves/games/{server_id}/versions/{version_id}")


def upload_game(token: str, local_dir: str, name: str, server_id: Optional[int] = None,
                progress_cb=None) -> Tuple[bool, object]:
    """把本地目录作为新版本上传；server_id 为空时先创建远端游戏。

    返回 (True, {"server_id", "version", "fingerprint"}) 或 (False, 错误)。
    """
    manifest = build_manifest(local_dir)
    ok, err = validate_client_manifest(manifest)
    if not ok:
        return False, err
    total = sum(int(m["size"]) for m in manifest)

    if server_id is None:
        server_id = _find_remote_game_id(token, name)
        if server_id is None:
            ok, res = create_remote_game(token, name)
            if not ok:
                return False, res
            server_id = res["id"]

    ok, res = _post_json(token, f"/saves/games/{server_id}/versions",
                         {"manifest": manifest, "total_size": total})
    if not ok:
        return False, res
    vid = res["versionId"]
    vnum = res["versionNumber"]

    # 增量：服务端会复用与上一版本 path+sha256 相同的文件，只回传需要上传的路径。
    # 兼容旧服务端：没有 uploadPaths 时按全量上传。
    upload_paths = res.get("uploadPaths")
    if upload_paths is None:
        to_upload = manifest
    else:
        want = set(upload_paths)
        to_upload = [m for m in manifest if m["path"] in want]

    total_files = len(to_upload)
    for i, m in enumerate(to_upload, 1):
        full = safe_join_local(local_dir, m["path"])
        url = f"{API_URL}/saves/games/{server_id}/versions/{vid}/files"
        def _do_upload():
            with open(full, "rb") as fh:
                return get_session().post(url, data={"path": m["path"], "sha256": m["sha256"]},
                                          files={"file": (os.path.basename(m["path"]), fh)},
                                          headers=_headers(token), timeout=UPLOAD_TIMEOUT)

        try:
            r = _send(_do_upload)
        except requests.exceptions.RequestException as e:
            delete_version(token, server_id, vid)
            return False, _friendly_error(e)
        if r.status_code == 409:
            delete_version(token, server_id, vid)
            return False, _detail_or_taken_over(r)
        if r.status_code >= 400:
            delete_version(token, server_id, vid)
            return False, _detail(r)
        if progress_cb:
            progress_cb(i, total_files, "上传中")

    ok, res = _post_json(token, f"/saves/games/{server_id}/versions/{vid}/commit")
    if not ok:
        return False, res
    return True, {"server_id": server_id, "version": vnum,
                  "fingerprint": tree_fingerprint(local_dir)}


def prepare_download(token: str, server_id: int, version_id: int, target_dir: str,
                     progress_cb=None) -> Tuple[bool, str]:
    """下载云端版本到 target_dir 的同级临时目录并逐个 sha256 校验。

    成功返回 (True, 临时目录路径)；失败返回 (False, 错误)。
    """
    ok, files = list_version_files(token, server_id, version_id)
    if not ok:
        return False, files

    tmp = target_dir.rstrip("\\/") + ".__download_tmp__"
    discard_download(tmp)
    os.makedirs(tmp, exist_ok=True)

    total = len(files)
    for i, f in enumerate(files, 1):
        rel = f["path"]
        try:
            dest = safe_join_local(tmp, rel)
        except ValueError as e:
            discard_download(tmp)
            return False, str(e)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        url = f"{API_URL}/saves/games/{server_id}/versions/{version_id}/files/download"
        try:
            r = _send(lambda: get_session().get(url, params={"path": rel}, headers=_headers(token),
                                                stream=True, timeout=UPLOAD_TIMEOUT))
        except requests.exceptions.RequestException as e:
            discard_download(tmp)
            return False, _friendly_error(e)
        if r.status_code == 409:
            discard_download(tmp)
            return False, TAKEN_OVER
        if r.status_code >= 400:
            discard_download(tmp)
            return False, _detail(r)
        with open(dest, "wb") as out:
            for chunk in r.iter_content(1024 * 1024):
                out.write(chunk)
        if sha256_file(dest) != f["sha256"]:
            discard_download(tmp)
            return False, f"校验失败: {rel}"
        if f.get("mtimeNs"):
            os.utime(dest, ns=(f["mtimeNs"], f["mtimeNs"]))
        if progress_cb:
            progress_cb(i, total, "下载中")
    return True, tmp


def apply_download(tmp: str, target: str) -> Tuple[bool, str]:
    """确认后应用：先把本地目标目录备份，再用临时目录覆盖；失败回滚。

    返回 (True, 备份路径或"") / (False, 错误)。
    """
    if not os.path.isdir(tmp):
        return False, "临时目录不存在"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target.rstrip("\\/") + f".bak.{ts}"
    moved_backup = False
    try:
        if os.path.exists(target):
            os.rename(target, backup)
            moved_backup = True
        os.rename(tmp, target)
        return True, backup if moved_backup else ""
    except Exception as e:
        if moved_backup and not os.path.exists(target) and os.path.exists(backup):
            try:
                os.rename(backup, target)
            except Exception:
                pass
        return False, str(e)


def discard_download(tmp: str) -> None:
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 后台 worker ----------------

class SaveSyncWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(bool, object)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    @Slot()
    def run(self):
        try:
            kwargs = dict(self._kwargs)
            kwargs.setdefault("progress_cb", self.progress.emit)
            ok_, res = self._fn(*self._args, **kwargs)
            self.finished.emit(bool(ok_), res)
        except Exception as e:
            self.finished.emit(False, str(e))
