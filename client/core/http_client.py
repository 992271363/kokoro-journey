"""共享 HTTP 客户端：统一 requests.Session 与代理策略。

背景：在 Windows 上 requests 默认会读取注册表里的系统代理（如 Clash），
大文件上传经本地代理转发时容易变慢甚至中途断开（SSLEOFError）。
这里默认**不走**系统/环境代理，用户可在设置里勾选「使用系统代理」开启。

settings.json 键：useSystemProxy（默认 False）。
"""
from __future__ import annotations

from typing import Optional

import requests
from requests.adapters import HTTPAdapter

from util.config import Settings

USE_PROXY_KEY = "useSystemProxy"
_POOL_SIZE = 8  # 与并发上传批次数匹配，复用连接避免重复 TLS 握手

_session: Optional[requests.Session] = None


def _apply_proxy(session: requests.Session) -> None:
    session.trust_env = bool(Settings().get(USE_PROXY_KEY, False))


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
