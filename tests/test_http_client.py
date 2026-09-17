"""共享 HTTP 客户端：代理策略（直连 / 系统代理 / 自定义 host:port）。"""
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

# --- 规范化 / 校验 ---
check("规范化 host:port",
      http_client.normalize_proxy_address("127.0.0.1:7897") == "http://127.0.0.1:7897")
check("规范化 带 scheme",
      http_client.normalize_proxy_address("http://127.0.0.1:7897") == "http://127.0.0.1:7897")
check("规范化 去空格",
      http_client.normalize_proxy_address("  127.0.0.1:7897 ") == "http://127.0.0.1:7897")
check("规范化 空 -> None", http_client.normalize_proxy_address("") is None)
check("校验 空合法", http_client.validate_proxy_address("")[0] is True)
check("校验 无端口非法", http_client.validate_proxy_address("127.0.0.1")[0] is False)
check("校验 非数字端口非法", http_client.validate_proxy_address("127.0.0.1:abc")[0] is False)
check("校验 端口越界非法", http_client.validate_proxy_address("127.0.0.1:99999")[0] is False)
check("校验 合法地址", http_client.validate_proxy_address("127.0.0.1:7897")[0] is True)

# --- 直连（未勾选，地址被忽略）---
s.set("useSystemProxy", False)
s.set("proxyAddress", "127.0.0.1:7899")
sess = http_client.get_session()
check("未勾选: 直连 trust_env=False", sess.trust_env is False)
check("未勾选: proxies 为空", not sess.proxies)

# --- 系统代理（勾选 + 地址留空）---
s.set("useSystemProxy", True)
s.set("proxyAddress", "")
sess = http_client.get_session()
check("勾选+空: 使用系统代理 trust_env=True", sess.trust_env is True)
check("勾选+空: proxies 为空", not sess.proxies)

# --- 自定义代理（勾选 + 地址）---
s.set("proxyAddress", "127.0.0.1:7899")
sess = http_client.get_session()
check("勾选+地址: trust_env=False", sess.trust_env is False)
check("勾选+地址: http/https 生效",
      sess.proxies.get("http") == "http://127.0.0.1:7899"
      and sess.proxies.get("https") == "http://127.0.0.1:7899")

# --- 非法地址 -> 回落系统代理 ---
s.set("proxyAddress", "127.0.0.1")
sess = http_client.get_session()
check("勾选+非法地址: 回落系统代理", sess.trust_env is True and not sess.proxies)

# --- refresh_proxy ---
s.set("useSystemProxy", False)
s.set("proxyAddress", "")
http_client.refresh_proxy()
check("refresh_proxy 生效", http_client.get_session().trust_env is False)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
