"""云存档客户端逻辑测试（离线，不联网）：清单/指纹/校验/安全路径/状态/落盘。"""
import _common  # noqa: F401

import os
import sys
import tempfile

import core.save_sync as ss

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


base = _common.tmpdir("kokoro_save_sync_")

# --- build_manifest ---
d = os.path.join(base, "save")
os.makedirs(os.path.join(d, "sub"))
with open(os.path.join(d, "b.sav"), "wb") as f:
    f.write(b"hello")
with open(os.path.join(d, "sub", "a.sav"), "wb") as f:
    f.write(b"world!")
manifest = ss.build_manifest(d)
check("manifest 条数", len(manifest) == 2)
check("manifest 路径排序", [m["path"] for m in manifest] == ["b.sav", "sub/a.sav"])
check("manifest 大小", manifest[1]["size"] == 6)
check("manifest 含 sha256", all(len(m["sha256"]) == 64 for m in manifest))
check("manifest 含 mtime_ns", all(isinstance(m["mtime_ns"], int) for m in manifest))

# --- 指纹随 mtime 变化 ---
fp1 = ss.tree_fingerprint(d)
fp2 = ss.tree_fingerprint(d)
check("指纹稳定", fp1 == fp2)
os.utime(os.path.join(d, "b.sav"), ns=(999999, 999999))
check("指纹随 mtime 变化", ss.tree_fingerprint(d) != fp1)

# --- validate_client_manifest ---
check("清单合法", ss.validate_client_manifest(manifest)[0])
check("单文件超 90MB 被拒", not ss.validate_client_manifest(
    [{"path": "x.sav", "size": ss.MAX_FILE_BYTES + 1, "sha256": "a" * 64}])[0])
check("总大小超 512MB 被拒", not ss.validate_client_manifest(
    [{"path": f"{i}", "size": 100 * 1024 * 1024, "sha256": "a" * 64} for i in range(6)])[0])
check("空清单被拒", not ss.validate_client_manifest([])[0])

# --- safe_join_local ---
check("安全路径正常", ss.safe_join_local(d, "sub/a.sav").endswith("a.sav"))


def raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


check("拒绝 .. 穿越", raises(lambda: ss.safe_join_local(d, "../evil")))
check("拒绝绝对路径", raises(lambda: ss.safe_join_local(d, "/etc/passwd")))
check("拒绝盘符路径", raises(lambda: ss.safe_join_local(d, "C:/x")))

# --- sync_status ---
check("状态: 未同步", ss.sync_status(False, False, False) == ss.STATUS_NOT_SYNCED)
check("状态: 一致", ss.sync_status(False, False, True) == ss.STATUS_IN_SYNC)
check("状态: 本地改动", ss.sync_status(True, False, True) == ss.STATUS_LOCAL)
check("状态: 云端更新", ss.sync_status(False, True, True) == ss.STATUS_CLOUD)
check("状态: 冲突", ss.sync_status(True, True, True) == ss.STATUS_CONFLICT)

# --- apply_download（备份 + 覆盖） ---
target = os.path.join(base, "local_game")
os.makedirs(target)
with open(os.path.join(target, "old.txt"), "wb") as f:
    f.write(b"OLD")
tmp = os.path.join(base, "local_game.__download_tmp__")
os.makedirs(tmp)
with open(os.path.join(tmp, "new.txt"), "wb") as f:
    f.write(b"NEW")
_mtime = 1_700_000_000_000_000_000  # 真实时间戳（100ns 粒度）
os.utime(os.path.join(tmp, "new.txt"), ns=(_mtime, _mtime))

ok_apply, backup = ss.apply_download(tmp, target)
check("apply 成功", ok_apply)
check("应用后新文件存在", os.path.exists(os.path.join(target, "new.txt")))
check("临时目录已消失", not os.path.exists(tmp))
check("备份存在且保留旧文件", backup and os.path.exists(os.path.join(backup, "old.txt")))
check("mtime 已恢复",
      abs(os.stat(os.path.join(target, "new.txt")).st_mtime_ns - _mtime) <= 1000)

# --- 上传重试 + 友好报错（离线 mock 网络） ---
class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.file_calls = 0

    def post(self, url, **kwargs):
        if url.endswith("/files-batch"):
            return _Resp(404, {"detail": "Not Found"})  # 走逐文件回退，覆盖重试逻辑
        if url.endswith("/files"):
            self.file_calls += 1
            if self.file_calls <= self.fail_times:
                raise ss.requests.exceptions.ConnectionError("boom")
            return _Resp(201, {"ok": True})
        if url.endswith("/versions"):
            return _Resp(201, {"versionId": 1, "versionNumber": 1})
        if url.endswith("/commit"):
            return _Resp(200, {"ok": True})
        return _Resp(200, {})

    def delete(self, url, **kwargs):
        return _Resp(200, {"ok": True})


ss.RETRY_BACKOFF = (0, 0, 0)  # 测试不等待退避

updir = os.path.join(base, "upload_game")
os.makedirs(updir)
with open(os.path.join(updir, "a.sav"), "wb") as f:
    f.write(b"data")

fake = _FakeSession(fail_times=2)
ss.get_session = lambda: fake
ok_up, res_up = ss.upload_game("tok", updir, "G", server_id=1)
check("上传: 两次中断后重试成功", ok_up and res_up.get("version") == 1)
check("上传: 文件请求共 3 次", fake.file_calls == 3)

fake2 = _FakeSession(fail_times=99)
ss.get_session = lambda: fake2
ok_up2, res_up2 = ss.upload_game("tok", updir, "G", server_id=1)
check("上传: 持续失败返回失败", not ok_up2)
check("上传: 失败信息为友好中文", isinstance(res_up2, str) and "网络" in res_up2)


# --- 同名复用远端游戏 id（不再重复 create） ---
class _CloudFake:
    def __init__(self, games):
        self.games = games
        self.created = 0

    def get(self, url, **kwargs):
        if url.endswith("/saves/games"):
            return _Resp(200, self.games)
        return _Resp(200, {})

    def post(self, url, **kwargs):
        if url.endswith("/saves/games"):
            self.created += 1
            return _Resp(201, {"id": 999, "name": "MyGame"})
        if url.endswith("/versions"):
            return _Resp(201, {"versionId": 1, "versionNumber": 1})
        if url.endswith("/files-batch"):
            return _Resp(404, {"detail": "Not Found"})
        if url.endswith("/files"):
            return _Resp(201, {"ok": True})
        if url.endswith("/commit"):
            return _Resp(200, {"ok": True})
        return _Resp(200, {})

    def delete(self, url, **kwargs):
        return _Resp(200, {"ok": True})


cloud = _CloudFake([{"id": 7, "name": "MyGame", "latestVersion": 1}])
ss.get_session = lambda: cloud
ok_reuse, res_reuse = ss.upload_game("tok", updir, "MyGame", server_id=None)
check("同名复用远端 id", ok_reuse and res_reuse["server_id"] == 7)
check("同名复用不再 create", cloud.created == 0)


# --- 409 语义区分（同名 vs 设备占用） ---
class _R409:
    def __init__(self, taken):
        self.status_code = 409
        self.headers = {"X-Cloud-Error": "taken_over"} if taken else {}

    def json(self):
        return {"detail": "同名游戏已存在"}


class _S409:
    def __init__(self, taken):
        self._taken = taken

    def post(self, url, **kwargs):
        return _R409(self._taken)


ss.get_session = lambda: _S409(False)
ok_d, res_d = ss.create_remote_game("tok", "X")
check("非设备 409 返回真实 detail", (not ok_d) and res_d == "同名游戏已存在")

ss.get_session = lambda: _S409(True)
ok_t, res_t = ss.create_remote_game("tok", "X")
check("设备 409 返回 TAKEN_OVER", (not ok_t) and res_t == ss.TAKEN_OVER)


# --- sha256 缓存：重复构建不重算 ---
calls = {"n": 0}
_orig_sha = ss.sha256_file


def _counting(path, *a, **k):
    calls["n"] += 1
    return _orig_sha(path, *a, **k)


ss.sha256_file = _counting
ss._SHA256_CACHE.clear()
ss.build_manifest(d)
n1 = calls["n"]
ss.build_manifest(d)
check("sha256 缓存: 第二次不再重算", calls["n"] == n1)
ss.sha256_file = _orig_sha


# --- 增量：只上传 uploadPaths 内文件 ---
class _IncrementalFake:
    def __init__(self):
        self.uploaded = []

    def post(self, url, **kw):
        if url.endswith("/versions"):
            return _Resp(201, {"versionId": 1, "versionNumber": 1,
                               "uploadPaths": ["sub/a.sav"]})
        if url.endswith("/files-batch"):
            return _Resp(404, {"detail": "Not Found"})
        if url.endswith("/files"):
            self.uploaded.append(kw.get("data", {}).get("path"))
            return _Resp(201, {"ok": True})
        if url.endswith("/commit"):
            return _Resp(200, {"ok": True})
        return _Resp(200, {})

    def get(self, url, **kw):
        return _Resp(200, [])

    def delete(self, url, **kw):
        return _Resp(200, {"ok": True})


inc = _IncrementalFake()
ss.get_session = lambda: inc
ok_inc, _res_inc = ss.upload_game("tok", d, "G", server_id=1)
check("增量: 只上传 uploadPaths 内文件", ok_inc and inc.uploaded == ["sub/a.sav"])


# --- 批量：多文件合并进一次请求 + 无批量接口时回退 ---
class _BatchFake:
    def __init__(self):
        self.batches = 0
        self.single = 0

    def post(self, url, **kw):
        if url.endswith("/versions"):
            return _Resp(201, {"versionId": 1, "versionNumber": 1,
                               "uploadPaths": ["b.sav", "sub/a.sav"]})
        if url.endswith("/files-batch"):
            self.batches += 1
            return _Resp(201, {"ok": True, "uploaded": []})
        if url.endswith("/files"):
            self.single += 1
            return _Resp(201, {"ok": True})
        if url.endswith("/commit"):
            return _Resp(200, {"ok": True})
        return _Resp(200, {})

    def get(self, url, **kw):
        return _Resp(200, [])

    def delete(self, url, **kw):
        return _Resp(200, {"ok": True})


bf = _BatchFake()
ss.get_session = lambda: bf
ok_b, _res_b = ss.upload_game("tok", d, "G", server_id=1)
check("批量: 多文件合并进 1 次请求", ok_b and bf.batches == 1 and bf.single == 0)


class _NoBatchFake(_BatchFake):
    def post(self, url, **kw):
        if url.endswith("/files-batch"):
            return _Resp(404, {"detail": "Not Found"})
        return super().post(url, **kw)


nb = _NoBatchFake()
ss.get_session = lambda: nb
ok_nb, _res_nb = ss.upload_game("tok", d, "G", server_id=1)
check("批量回退: 无批量接口时逐文件上传", ok_nb and nb.batches == 0 and nb.single == 2)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
