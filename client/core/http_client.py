"""共享 HTTP 客户端：统一 requests.Session 与代理策略。

背景：在 Windows 上 requests 默认会读取注册表里的系统代理（如 Clash），
大文件上传经本地代理转发时容易变慢甚至中途断开（SSLEOFError）。
这里默认**不走**系统/环境代理，用户可在设置里配置三态：

- 未勾选「使用系统代理」→ 直连（trust_env=False，忽略系统/环境代理）
- 勾选且「代理地址」留空 → 使用系统代理（trust_env=True）
- 勾选且填写代理地址（host:port）→ 走显式代理（trust_env=False）

settings.json 键：useSystemProxy（bool，默认 False）、proxyAddress（str，默认空）。
"""
from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter

from util.config import Settings

USE_PROXY_KEY = "useSystemProxy"
PROXY_ADDRESS_KEY = "proxyAddress"
_POOL_SIZE = 8  # 与并发上传批次数匹配，复用连接避免重复 TLS 握手

_session: Optional[requests.Session] = None


def normalize_proxy_address(raw) -> Optional[str]:
    """把用户输入的代理地址规范为 http://host:port；非法或为空返回 None。

    允许 "127.0.0.1:7897" 或 "http://127.0.0.1:7897"；空串表示"使用系统代理"。
    """
    addr = str(raw or "").strip()
    if not addr:
        return None
    if "://" not in addr:
        addr = "http://" + addr
    try:
        parts = urlsplit(addr)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = parts.hostname
    if not host or port is None or not (1 <= port <= 65535):
        return None
    return f"{parts.scheme}://{host}:{port}"


def validate_proxy_address(raw) -> Tuple[bool, str]:
    """校验代理地址；空串合法（=使用系统代理）。返回 (ok, 错误信息)。"""
    addr = str(raw or "").strip()
    if not addr:
        return True, ""
    if normalize_proxy_address(addr) is None:
        return False, "代理地址无效，请填写 host:port（如 127.0.0.1:7897）。"
    return True, ""


def _apply_proxy(session: requests.Session) -> None:
    if not bool(Settings().get(USE_PROXY_KEY, False)):
        session.trust_env = False
        session.proxies = {}
        return
    addr = normalize_proxy_address(Settings().get(PROXY_ADDRESS_KEY, ""))
    if addr:
        session.trust_env = False
        session.proxies = {"http": addr, "https": addr}
    else:
        session.proxies = {}
        session.trust_env = True


def get_session() -> requests.Session:
    """返回进程级共享 Session，并按当前设置应用代理策略。"""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = HTTPAdapter(pool_connections=_POOL_SIZE, pool_maxsize=_POOL_SIZE)
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    _apply_proxy(_session)
    return _session


def refresh_proxy() -> None:
    """设置变更后重新应用代理策略。"""
    if _session is not None:
        _apply_proxy(_session)
