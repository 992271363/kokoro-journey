"""云存档接口测试（SQLite + TestClient，无需 MariaDB；文件落到临时 SAVES_DIR）。"""
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

# 必须在导入 app 之前设置
os.environ.setdefault("SECRET_KEY", "test-secret-key")
_SAVES_DIR = _common.tmpdir("kokoro_saves_api_")
os.environ["SAVES_DIR"] = _SAVES_DIR

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_db_path = _common.tmpfile("kokoro_saves_api_", ".db")
_test_engine = _real_create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
sqlalchemy.create_engine = lambda *a, **k: _test_engine

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, database, models, main  # noqa: E402

client = TestClient(main.app)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# 建用户并生成 token
session = database.SessionLocal()
user = models.User(username="tester", hashed_password="x")
session.add(user)
session.commit()
uid = user.id
session.close()

token = auth.create_access_token({"sub": "tester"})
H = {"Authorization": f"Bearer {token}", "X-Device-Id": "dev-A"}

# --- 建游戏 / 重名 ---
r = client.post("/saves/games", json={"name": "Game A"}, headers=H)
check("建游戏 201", r.status_code == 201)
game_id = r.json()["id"]
check("重名游戏 409", client.post("/saves/games", json={"name": "Game A"}, headers=H).status_code == 409)
r = client.post("/saves/games", json={"name": "Game A"}, headers=H)
check("重名 409 不带设备标记", r.headers.get("x-cloud-error") != "taken_over")

# --- 开版本 + 上传 + 提交 ---
content = b"save-data-123"
digest = hashlib.sha256(content).hexdigest()
manifest = {
    "manifest": [{"path": "save/a.sav", "size": len(content), "sha256": digest, "mtime_ns": 123}],
    "total_size": len(content),
}
r = client.post(f"/saves/games/{game_id}/versions", json=manifest, headers=H)
check("开版本 201", r.status_code == 201)
vid = r.json()["versionId"]

r = client.post(
    f"/saves/games/{game_id}/versions/{vid}/files",
    data={"path": "save/a.sav", "sha256": digest},
    files={"file": ("a.sav", content)},
    headers=H,
)
check("上传文件 201", r.status_code == 201)

r = client.post(f"/saves/games/{game_id}/versions/{vid}/commit", headers=H)
check("提交版本 200", r.status_code == 200)

expected = os.path.join(_SAVES_DIR, str(uid), str(game_id), "v1", "save", "a.sav")
check("版本文件已落盘", os.path.isfile(expected))

# --- 列表 / 文件清单 / 下载 ---
r = client.get(f"/saves/games/{game_id}/versions", headers=H)
check("版本列表", r.status_code == 200 and len(r.json()) == 1 and r.json()[0]["versionNumber"] == 1)

r = client.get(f"/saves/games/{game_id}/versions/{vid}/files", headers=H)
check("文件清单", r.status_code == 200 and r.json()[0]["path"] == "save/a.sav")

r = client.get(f"/saves/games/{game_id}/versions/{vid}/files/download", params={"path": "save/a.sav"}, headers=H)
check("下载内容一致", r.status_code == 200 and r.content == content)

# --- 安全：路径穿越 / 超限 ---
bad = {"manifest": [{"path": "../evil", "size": 1, "sha256": "a" * 64}], "total_size": 1}
check("路径穿越被拒", client.post(f"/saves/games/{game_id}/versions", json=bad, headers=H).status_code == 400)

oversize_file = {"manifest": [{"path": "big.sav", "size": 100 * 1024 * 1024 + 1, "sha256": "a" * 64}], "total_size": 100 * 1024 * 1024 + 1}
check("单文件超限被拒", client.post(f"/saves/games/{game_id}/versions", json=oversize_file, headers=H).status_code == 400)

oversize_total = {"manifest": [{"path": f"{i}.sav", "size": 100 * 1024 * 1024, "sha256": "a" * 64} for i in range(6)], "total_size": 600 * 1024 * 1024}
check("总大小超限被拒", client.post(f"/saves/games/{game_id}/versions", json=oversize_total, headers=H).status_code == 400)

# --- 增量复用：v2 只上传变化的文件 ---
content_b = b"save-data-456"
digest_b = hashlib.sha256(content_b).hexdigest()
manifest2 = {
    "manifest": [
        {"path": "save/a.sav", "size": len(content), "sha256": digest, "mtime_ns": 123},
        {"path": "save/b.sav", "size": len(content_b), "sha256": digest_b, "mtime_ns": 456},
    ],
    "total_size": len(content) + len(content_b),
}
r = client.post(f"/saves/games/{game_id}/versions", json=manifest2, headers=H)
check("v2 开版本 201", r.status_code == 201)
vid2 = r.json()["versionId"]
check("v2 仅需上传变化文件", r.json().get("uploadPaths") == ["save/b.sav"])

r = client.post(
    f"/saves/games/{game_id}/versions/{vid2}/files",
    data={"path": "save/b.sav", "sha256": digest_b},
    files={"file": ("b.sav", content_b)},
    headers=H,
)
check("v2 上传变化文件 201", r.status_code == 201)
check("v2 提交 200", client.post(f"/saves/games/{game_id}/versions/{vid2}/commit", headers=H).status_code == 200)

_gdir = os.path.join(_SAVES_DIR, str(uid), str(game_id))
check("v2 复用文件已就位", os.path.isfile(os.path.join(_gdir, "v2", "save", "a.sav")))
check("v2 新文件已落盘", os.path.isfile(os.path.join(_gdir, "v2", "save", "b.sav")))
r = client.get(f"/saves/games/{game_id}/versions/{vid2}/files/download", params={"path": "save/a.sav"}, headers=H)
check("v2 复用文件内容一致", r.status_code == 200 and r.content == content)

# --- 批量上传：一次请求传多个文件 ---
content_c = b"save-data-789"
digest_c = hashlib.sha256(content_c).hexdigest()
content_d = b"save-data-abc"
digest_d = hashlib.sha256(content_d).hexdigest()
manifest3 = {
    "manifest": [
        {"path": "save/c.sav", "size": len(content_c), "sha256": digest_c, "mtime_ns": 1},
        {"path": "save/d.sav", "size": len(content_d), "sha256": digest_d, "mtime_ns": 2},
    ],
    "total_size": len(content_c) + len(content_d),
}
r = client.post(f"/saves/games/{game_id}/versions", json=manifest3, headers=H)
check("v3 开版本 201", r.status_code == 201)
vid3 = r.json()["versionId"]
check("v3 两文件都需上传", sorted(r.json().get("uploadPaths") or []) == ["save/c.sav", "save/d.sav"])

items = json.dumps([{"path": "save/c.sav", "sha256": digest_c},
                    {"path": "save/d.sav", "sha256": digest_d}])
r = client.post(
    f"/saves/games/{game_id}/versions/{vid3}/files-batch",
    data={"items": items},
    files=[("files", ("c.sav", content_c)), ("files", ("d.sav", content_d))],
    headers=H,
)
check("批量上传 201", r.status_code == 201)
check("批量返回 uploaded", sorted(r.json().get("uploaded") or []) == ["save/c.sav", "save/d.sav"])
check("v3 提交 200", client.post(f"/saves/games/{game_id}/versions/{vid3}/commit", headers=H).status_code == 200)
r = client.get(f"/saves/games/{game_id}/versions/{vid3}/files/download", params={"path": "save/d.sav"}, headers=H)
check("批量上传内容一致", r.status_code == 200 and r.content == content_d)

# --- 批量下载（内存 zip）---
r = client.post(f"/saves/games/{game_id}/versions/{vid3}/files-batch-download",
                json={"paths": ["save/c.sav", "save/d.sav"]}, headers=H)
check("批量下载 200", r.status_code == 200)
zipped = {}
if r.status_code == 200:
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        for name in zf.namelist():
            zipped[name] = zf.read(name)
check("批量下载内容正确",
      zipped.get("save/c.sav") == content_c and zipped.get("save/d.sav") == content_d)

# --- list_games 带回 latestVersionId ---
r = client.get("/saves/games", headers=H)
g = next((x for x in r.json() if x["id"] == game_id), None)
check("list_games 含 latestVersionId", bool(g) and g.get("latestVersionId") == vid3)

# --- 单设备接管 ---
r = client.post("/saves/device/claim", headers={"Authorization": f"Bearer {token}", "X-Device-Id": "dev-B"})
check("新设备登记成功", r.status_code == 200 and r.json()["previousDeviceId"] == "dev-A")
r = client.get("/saves/games", headers=H)
check("旧设备云操作被拒(409)", r.status_code == 409)
check("设备冲突带 X-Cloud-Error 头", r.headers.get("x-cloud-error") == "taken_over")
HB = {"Authorization": f"Bearer {token}", "X-Device-Id": "dev-B"}
check("新设备云操作可用", client.get("/saves/games", headers=HB).status_code == 200)

try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
