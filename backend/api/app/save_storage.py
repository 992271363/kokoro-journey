"""云存档文件系统存储层。

职责：
- 安全的相对路径校验与拼接（防路径穿越）
- 版本目录 / 临时目录命名
- 单文件 SHA-256
- 清单校验（路径、大小、sha256、总大小上限）
- 原子提交、版本剪裁、目录删除

磁盘布局：
    <root>/<user_id>/<game_id>/v<N>/<relative_path>
上传期间：
    <root>/<user_id>/<game_id>/.tmp_<version_id>/<relative_path>
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from typing import Iterable

# 服务端兜底上限（客户端会更早拦截）
MAX_TOTAL_BYTES = 512 * 1024 * 1024   # 单版本总大小
MAX_FILE_BYTES = 100 * 1024 * 1024    # 单文件硬上限
KEEP_VERSIONS = 10                    # 每个游戏保留最近版本数

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_DIR_RE = re.compile(r"^v(\d+)$")

SAVES_ROOT = os.environ.get("SAVES_DIR", "/app/saves")


def _root(root: str | None = None) -> str:
    return os.path.abspath(root or SAVES_ROOT)


def safe_relpath(path: str) -> str:
    """把客户端给出的相对路径规范化，并拒绝一切越界/非法形式。

    返回使用 '/' 分隔的规范相对路径；非法则抛 ValueError。
    """
    if path is None:
        raise ValueError("路径为空")
    s = str(path).replace("\\", "/").strip()
    if not s or s in (".", ".."):
        raise ValueError("路径为空")
    if s.startswith("/"):
        raise ValueError("不允许绝对路径")
    if len(s) >= 2 and s[1] == ":":
        raise ValueError("不允许盘符路径")
    parts: list[str] = []
    for seg in s.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise ValueError("不允许路径穿越")
        if any(ord(c) < 32 for c in seg):
            raise ValueError("路径包含非法字符")
        parts.append(seg)
    if not parts:
        raise ValueError("路径为空")
    return "/".join(parts)


def safe_join(root: str | None, *parts: str) -> str:
    """在 root 内安全拼接路径，结果必须仍位于 root 之下。"""
    base = _root(root)
    target = os.path.abspath(os.path.join(base, *parts))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("路径越出存储根目录")
    return target


def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def game_dir(user_id: int, game_id: int, root: str | None = None) -> str:
    return safe_join(root, str(user_id), str(game_id))


def version_dir(user_id: int, game_id: int, version_number: int, root: str | None = None) -> str:
    return safe_join(root, str(user_id), str(game_id), f"v{version_number}")


def temp_dir(user_id: int, game_id: int, version_id: int, root: str | None = None) -> str:
    return safe_join(root, str(user_id), str(game_id), f".tmp_{version_id}")


def validate_manifest(manifest: Iterable[dict],
                      max_total: int = MAX_TOTAL_BYTES,
                      max_file: int = MAX_FILE_BYTES) -> None:
    """校验清单：路径合法且不重复、大小合理、sha256 合法、总大小受限。

    非法则抛 ValueError。
    """
    seen: set[str] = set()
    total = 0
    count = 0
    for item in manifest:
        rel = safe_relpath(item.get("path"))
        if rel in seen:
            raise ValueError(f"清单存在重复路径: {rel}")
        seen.add(rel)

        size = item.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"非法大小: {rel}")
        if size > max_file:
            raise ValueError(f"单文件超过上限: {rel}")
        total += size
        count += 1

        digest = str(item.get("sha256", "")).lower()
        if not _SHA256_RE.match(digest):
            raise ValueError(f"非法 sha256: {rel}")

    if count == 0:
        raise ValueError("清单为空")
    if total > max_total:
        raise ValueError("总大小超过上限")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def atomic_commit(temp: str, final: str) -> None:
    """把临时目录原子改名为最终版本目录；最终目录已存在则抛错。"""
    if os.path.exists(final):
        raise FileExistsError(f"目标版本目录已存在: {final}")
    parent = os.path.dirname(final)
    ensure_dir(parent)
    os.replace(temp, final)


def list_version_numbers(game_path: str) -> list[int]:
    if not os.path.isdir(game_path):
        return []
    nums: list[int] = []
    for name in os.listdir(game_path):
        m = _VERSION_DIR_RE.match(name)
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def prune_versions(game_path: str, keep: int = KEEP_VERSIONS) -> list[int]:
    """删除最旧的版本目录，仅保留最新 keep 个；返回被删除的版本号。"""
    nums = list_version_numbers(game_path)
    if len(nums) <= keep:
        return []
    to_delete = nums[: len(nums) - keep]
    for n in to_delete:
        shutil.rmtree(os.path.join(game_path, f"v{n}"), ignore_errors=True)
    return to_delete


def remove_tree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def next_version_number(game_path: str) -> int:
    nums = list_version_numbers(game_path)
    return (max(nums) + 1) if nums else 1
