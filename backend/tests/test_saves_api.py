"""云存档接口测试（SQLite + TestClient，无需 MariaDB；文件落到临时 SAVES_DIR）。"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

# 必须在导入 app 之前设置
os.environ.setdefault("SECRET_KEY", "test-secret-key")
_SAVES_DIR = tempfile.mkdtemp(prefix="kokoro_saves_api_")
os.environ["SAVES_DIR"] = _SAVES_DIR

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_fd, _db_path = tempfile.mkstemp(prefix="kokoro_saves_api_", suffix=".db")
os.close(_fd)
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

# --- 单设备接管 ---
r = client.post("/saves/device/claim", headers={"Authorization": f"Bearer {token}", "X-Device-Id": "dev-B"})
check("新设备登记成功", r.status_code == 200 and r.json()["previousDeviceId"] == "dev-A")
check("旧设备云操作被拒(409)", client.get("/saves/games", headers=H).status_code == 409)
HB = {"Authorization": f"Bearer {token}", "X-Device-Id": "dev-B"}
check("新设备云操作可用", client.get("/saves/games", headers=HB).status_code == 200)

try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
