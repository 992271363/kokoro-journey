"""Locale Emulator（LE）调用辅助。

用户在设置里指定 LE 根目录；这里负责：
- 在根目录（含一层子目录）内定位 LEProc.exe 与 LEConfig.xml；
- 解析 LEConfig.xml 得到「区域配置」列表（名称/编号/区域/是否需管理员/是否主菜单）；
- 组装并执行 `LEProc.exe -runas <编号> "<目标>"`（用法取自 LEProc 自身的使用说明）。

不涉及界面与数据库；界面/启动逻辑调用本模块的纯函数。
"""
from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

LEPROC_NAME = "LEProc.exe"
LECONFIG_NAME = "LEConfig.xml"

_GUID_RE = re.compile(
    r"^\{?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}?$"
)


def _find_in_root(root: Optional[str], filename: str) -> Optional[str]:
    """在根目录（含一层子目录）内找文件；找不到返回 None。"""
    if not root or not os.path.isdir(root):
        return None
    direct = os.path.join(root, filename)
    if os.path.isfile(direct):
        return direct
    try:
        entries = os.listdir(root)
    except OSError:
        return None
    for name in entries:
        sub = os.path.join(root, name)
        if os.path.isdir(sub):
            candidate = os.path.join(sub, filename)
            if os.path.isfile(candidate):
                return candidate
    return None


def find_leproc(root: Optional[str]) -> Optional[str]:
    return _find_in_root(root, LEPROC_NAME)


def find_leconfig(root: Optional[str]) -> Optional[str]:
    return _find_in_root(root, LECONFIG_NAME)


def normalize_guid(guid: Optional[str]) -> str:
    """统一为小写、去掉花括号的编号字符串。"""
    return (guid or "").strip().strip("{}").strip().lower()


def is_valid_guid(guid: Optional[str]) -> bool:
    return bool(_GUID_RE.match((guid or "").strip()))


def _truthy(text: Optional[str]) -> bool:
    return (text or "").strip().lower() in ("true", "1", "yes")


def parse_profiles(config_path: Optional[str]) -> List[dict]:
    """解析 LEConfig.xml 中的区域配置；失败或无有效项时返回空列表。

    返回项：{guid, name, location, run_as_admin, main_menu}
    """
    if not config_path or not os.path.isfile(config_path):
        return []
    try:
        root = ET.parse(config_path).getroot()
    except Exception:
        return []

    profiles: List[dict] = []
    for node in root.iter("Profile"):
        guid = node.get("Guid") or ""
        if not is_valid_guid(guid):
            continue
        child = {c.tag: (c.text or "").strip() for c in node}
        profiles.append({
            "guid": normalize_guid(guid),
            "name": (node.get("Name") or "").strip() or normalize_guid(guid),
            "location": child.get("Location", ""),
            "run_as_admin": _truthy(child.get("RunAsAdmin")),
            "main_menu": _truthy(node.get("MainMenu")),
        })
    return profiles


def pick_default_index(profiles: List[dict]) -> int:
    """默认选中项：优先「主菜单」；否则名字/区域带日语；否则第一项。"""
    if not profiles:
        return -1
    for index, item in enumerate(profiles):
        if item.get("main_menu"):
            return index
    for index, item in enumerate(profiles):
        name = (item.get("name") or "").lower()
        location = (item.get("location") or "").lower()
        if "japan" in name or location.startswith("ja"):
            return index
    return 0


def profile_label(item: dict) -> str:
    """下拉里显示的文字：名称（区域，管理员）。"""
    parts = [item.get("location") or "?"]
    if item.get("run_as_admin"):
        parts.append("需管理员")
    return f"{item.get('name')}（{', '.join(parts)}）"


def check_ready(root: Optional[str], guid: Optional[str]) -> Tuple[bool, str]:
    """检查能否用 LE 启动；返回 (是否就绪, 原因)。"""
    if not root or not os.path.isdir(root):
        return False, "尚未设置 Locale Emulator 文件夹"
    if not find_leproc(root):
        return False, f"在该文件夹里找不到 {LEPROC_NAME}"
    if not is_valid_guid(guid):
        return False, "尚未选择默认区域配置"
    return True, ""


def build_le_command(leproc: str, guid: str, target: str) -> List[str]:
    """组装启动命令（用法来自 LEProc：-runas <编号> <目标>）。"""
    return [leproc, "-runas", normalize_guid(guid), target]


def launch_with_le(leproc: str, guid: str, target: str) -> Tuple[bool, str]:
    """通过 LE 启动目标程序；返回 (是否成功, 错误说明)。"""
    if not os.path.isfile(leproc):
        return False, "找不到 Locale Emulator 的启动程序"
    if not os.path.isfile(target):
        return False, "启动目标不存在"
    if not is_valid_guid(guid):
        return False, "区域配置无效"

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        subprocess.Popen(build_le_command(leproc, guid, target),
                         cwd=os.path.dirname(target) or None, **kwargs)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)
