"""登录凭据：账号历史 / DPAPI 密码往返 / 自动登录凭据（隔离设置目录）。"""
import _common  # noqa: F401

import sys

from util import credentials as c
from util.config import Settings

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# 账号历史（最多 10，最近在前）
for i in range(12):
    c.add_account(f"user{i}")
hist = c.get_accounts()
check("历史最多保留 10", len(hist) == 10)
check("最近账号在最前", hist[0] == "user11")
check("重复添加去重置顶", (c.add_account("user5"), c.get_accounts()[0] == "user5")[1])

# 密码 DPAPI 往返
c.save_password("alice", "secret123")
check("密码可解密还原", c.get_password("alice") == "secret123")
c.clear_password("alice")
check("清除后无密码", c.get_password("alice") is None)

# 自动登录凭据
c.set_auto_login(True, "alice")
c.save_password("alice", "pw!")
check("自动登录凭据", c.get_auto_login_credentials() == ("alice", "pw!"))
c.set_auto_login(False)
check("关闭自动登录后无凭据", c.get_auto_login_credentials() is None)

# 删除账号会清理密码与自动登录用户
c.add_account("bob")
c.save_password("bob", "x")
c.set_auto_login(True, "bob")
c.remove_account("bob")
check("删除账号后密码清除", c.get_password("bob") is None)
check("删除账号后自动登录用户清除", Settings().get("autoLoginUser") is None)
check("删除账号后历史不含 bob", "bob" not in c.get_accounts())

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
