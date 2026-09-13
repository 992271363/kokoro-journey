"""云存档存储层测试：路径安全 / 清单校验 / 原子提交 / 版本剪裁。"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

from app import save_storage as ss  # noqa: E402

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


root = tempfile.mkdtemp(prefix="kokoro_saves_test_")

# --- safe_relpath ---
check("safe_relpath 普通路径", ss.safe_relpath("a/b/c.txt") == "a/b/c.txt")
check("safe_relpath 反斜杠归一", ss.safe_relpath("a\\b\\c") == "a/b/c")
check("safe_relpath 忽略 . 段", ss.safe_relpath("a/./b") == "a/b")
check("safe_relpath 拒绝 ..", raises(lambda: ss.safe_relpath("../x")))
check("safe_relpath 拒绝绝对路径", raises(lambda: ss.safe_relpath("/abs/x")))
check("safe_relpath 拒绝盘符", raises(lambda: ss.safe_relpath("C:/x")))
check("safe_relpath 拒绝空", raises(lambda: ss.safe_relpath("  ")))

# --- safe_join ---
check("safe_join 正常", ss.safe_join(root, "1", "2").startswith(os.path.abspath(root)))
check("safe_join 拒绝越界", raises(lambda: ss.safe_join(root, "..", "evil")))

# --- sha256_file ---
f = os.path.join(root, "hello.bin")
with open(f, "wb") as fh:
    fh.write(b"hello world")
expect = hashlib.sha256(b"hello world").hexdigest()
check("sha256_file 正确", ss.sha256_file(f) == expect)

# --- validate_manifest ---
good = [{"path": "a.sav", "size": 10, "sha256": "a" * 64}]
check("清单合法", not raises(lambda: ss.validate_manifest(good)))
check("清单重复路径被拒", raises(lambda: ss.validate_manifest(
    [{"path": "a.sav", "size": 1, "sha256": "a" * 64},
     {"path": "a.sav", "size": 1, "sha256": "a" * 64}])))
check("清单非法 sha256 被拒", raises(lambda: ss.validate_manifest(
    [{"path": "a.sav", "size": 1, "sha256": "zz"}])))
check("清单单文件超限被拒", raises(lambda: ss.validate_manifest(
    [{"path": "a.sav", "size": ss.MAX_FILE_BYTES + 1, "sha256": "a" * 64}])))
check("清单总大小超限被拒", raises(lambda: ss.validate_manifest(
    [{"path": f"{i}.sav", "size": 100 * 1024 * 1024, "sha256": "a" * 64} for i in range(6)])))
check("清单为空被拒", raises(lambda: ss.validate_manifest([])))

# --- 目录 + 原子提交 ---
u, g, vid = 1, 2, 3
tdir = ss.temp_dir(u, g, vid, root)
ss.ensure_dir(tdir)
with open(os.path.join(tdir, "save.dat"), "wb") as fh:
    fh.write(b"data")
vdir = ss.version_dir(u, g, 1, root)
ss.atomic_commit(tdir, vdir)
check("原子提交后文件就位", os.path.exists(os.path.join(vdir, "save.dat")))
check("原子提交后临时目录消失", not os.path.exists(tdir))
check("重复提交被拒", raises(lambda: ss.atomic_commit(tdir, vdir)))

# --- 版本剪裁 ---
gpath = ss.game_dir(u, g, root)
for n in range(2, 13):
    os.makedirs(os.path.join(gpath, f"v{n}"), exist_ok=True)
check("next_version_number", ss.next_version_number(gpath) == 13)
deleted = ss.prune_versions(gpath, keep=10)
check("剪裁删除最旧版本", deleted == [1, 2])
check("剪裁后保留 10 版", len(ss.list_version_numbers(gpath)) == 10)
check("剪裁后最旧为 v3", ss.list_version_numbers(gpath)[0] == 3)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
