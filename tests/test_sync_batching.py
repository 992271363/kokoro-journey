"""会话分批上传：按条数/字节切块、失败只标记已成功部分、空数据。"""
import _common  # noqa: F401

import json
import sys

import core.sync as sync

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


sent = []
marked = []
results = []


def fake_send(chunk, endpoint, token, timeout=30):
    sent.append({"endpoint": endpoint, "chunk": [dict(x) for x in chunk]})
    return results.pop(0) if results else True


def fake_mark(batch):
    marked.extend(batch)


sync.send_data_to_api = fake_send
sync.mark_sessions_as_synced = fake_mark


def reset(rets=None):
    sent.clear()
    marked.clear()
    results.clear()
    if rets:
        results.extend(rets)


def est(item):
    return len(json.dumps(item, ensure_ascii=False).encode("utf-8"))


# --- 1) 按条数切块 ---
data = [{"i": k} for k in range(5)]
sessions = list(range(5))
reset()
ok_, up = sync.sync_sessions_batched(data, sessions, "t", batch_size=2, max_bytes=10 ** 9)
check("条数分批: 全部成功", ok_ is True and up == 5)
check("条数分批: 块数=3", len(sent) == 3)
check("条数分批: 各块大小 [2,2,1]", [len(s["chunk"]) for s in sent] == [2, 2, 1])
check("条数分批: 全部标记", marked == [0, 1, 2, 3, 4])
check("条数分批: endpoint 正确", all(s["endpoint"] == "/sync/sessions/" for s in sent))

# --- 2) 按字节切块 ---
data = [{"blob": "x" * 1000} for _ in range(5)]
sessions = list(range(5))
reset()
ok_, up = sync.sync_sessions_batched(data, sessions, "t", batch_size=1000, max_bytes=2500)
check("字节分批: 全部成功", ok_ is True and up == 5)
check("字节分批: 多于 1 块", len(sent) >= 2)
fits = all(
    sum(est(x) for x in s["chunk"]) <= 2500 or len(s["chunk"]) == 1
    for s in sent
)
check("字节分批: 每块不超上限(单条除外)", fits)

# --- 3) 中途失败：只标记已成功部分 ---
data = [{"i": k} for k in range(4)]
sessions = list(range(4))
reset(rets=[True, False])
ok_, up = sync.sync_sessions_batched(data, sessions, "t", batch_size=2, max_bytes=10 ** 9)
check("失败: 返回失败", ok_ is False)
check("失败: 已成功条数=2", up == 2)
check("失败: 只标记前 2 条", marked == [0, 1])
check("失败: 只发送 2 批", len(sent) == 2)

# --- 4) 空数据 ---
reset()
ok_, up = sync.sync_sessions_batched([], [], "t")
check("空数据: 成功且 0 条", ok_ is True and up == 0)
check("空数据: 未发送", len(sent) == 0)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
