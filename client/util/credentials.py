"""登录凭据存储。

- 账号历史：明文（settings.json）
- 密码：Windows DPAPI 加密后以 base64 存入 settings.json（仅当前 Windows 用户可解密）
- “记住密码”与“自动登录”分开控制
"""
from __future__ import annotations

import base64
from typing import List, Optional, Tuple

import win32crypt

from util.config import Settings


def _protect(data: bytes) -> bytes:
    return win32crypt.CryptProtectData(data, None, None, None, None, 0)


def _unprotect(blob: bytes) -> Optional[bytes]:
    try:
        _desc, out = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
        return out
    except Exception:
        return None


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# ---------------- 账号历史 ----------------

def get_accounts() -> List[str]:
    return list(Settings().get("accountHistory", []) or [])


def add_account(username: str) -> None:
    username = (username or "").strip()
    if not username:
        return
    accounts = get_accounts()
    if username in accounts:
        accounts.remove(username)
    accounts.insert(0, username)
    del accounts[10:]  # 最多保留 10 个
    Settings().set("accountHistory", accounts)


def remove_account(username: str) -> None:
    accounts = get_accounts()
    if username in accounts:
        accounts.remove(username)
        Settings().set("accountHistory", accounts)
    clear_password(username)
    if Settings().get("autoLoginUser") == username:
        Settings().set("autoLoginUser", None)


# ---------------- 密码 ----------------

def _saved_passwords() -> dict:
    return dict(Settings().get("savedPasswords", {}) or {})


def save_password(username: str, password: str) -> None:
    if not username:
        return
    store = _saved_passwords()
    store[username] = _b64(_protect(password.encode("utf-8")))
    Settings().set("savedPasswords", store)


def get_password(username: str) -> Optional[str]:
    store = _saved_passwords()
    blob = store.get(username)
    if not blob:
        return None
    raw = _unprotect(_unb64(blob))
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except Exception:
        return None


def clear_password(username: str) -> None:
    store = _saved_passwords()
    if username in store:
        del store[username]
        Settings().set("savedPasswords", store)


# ---------------- 自动登录 ----------------

def set_auto_login(enabled: bool, username: str = "") -> None:
    Settings().set("autoLogin", bool(enabled))
    if enabled and username:
        Settings().set("autoLoginUser", username)


def is_auto_login() -> bool:
    return bool(Settings().get("autoLogin", False))


def get_auto_login_credentials() -> Optional[Tuple[str, str]]:
    """返回 (username, password)；未开启自动登录或缺少凭据时返回 None。"""
    if not is_auto_login():
        return None
    username = Settings().get("autoLoginUser")
    if not username:
        return None
    password = get_password(username)
    if not password:
        return None
    return username, password
