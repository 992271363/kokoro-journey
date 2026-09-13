"""共享 HTTP 客户端：代理开关（默认直连，可切换使用系统代理）。"""
import _common  # noqa: F401

import sys

from util.config import Settings
from core import http_client

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


s = Settings()
s.set("useSystemProxy", False)
check("默认直连 trust_env=False", http_client.get_session().trust_env is False)

s.set("useSystemProxy", True)
check("开启系统代理 trust_env=True", http_client.get_session().trust_env is True)

s.set("useSystemProxy", False)
http_client.refresh_proxy()
check("refresh_proxy 生效", http_client.get_session().trust_env is False)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
