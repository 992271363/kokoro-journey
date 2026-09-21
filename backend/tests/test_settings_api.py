"""用户背景图库接口测试（SQLite + TestClient；文件落到临时 UPLOADS_DIR）。"""
import io
import os
import sys
from pathlib import Path

BACKEND_API = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(BACKEND_API))

import _common  # noqa: E402

# 必须在导入 app 之前设置
os.environ.setdefault("SECRET_KEY", "test-secret-key")
_UPLOADS_DIR = _common.tmpdir("kokoro_uploads_")
os.environ["UPLOADS_DIR"] = _UPLOADS_DIR

import sqlalchemy  # noqa: E402

_real_create_engine = sqlalchemy.create_engine
_db_path = _common.tmpfile("kokoro_settings_", ".db")
_test_engine = _real_create_engine(f"sqlite:///{_db_path}",
                                   connect_args={"check_same_thread": False})
sqlalchemy.create_engine = lambda *a, **k: _test_engine

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app import auth, database, models, main  # noqa: E402

client = TestClient(main.app)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def image_bytes(fmt="PNG", size=(64, 48), color=(20, 40, 80)):
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# 建用户并生成 token
session = database.SessionLocal()
user = models.User(username="bguser", hashed_password="x")
session.add(user)
session.commit()
session.close()

token = auth.create_access_token({"sub": "bguser"})
H = {"Authorization": f"Bearer {token}"}

# --- 初始状态 ---
r = client.get("/settings/background", headers=H)
check("初始为默认 BG1", r.status_code == 200 and r.json()["background"] == "default:BG1")
check("初始图库为空", r.json()["uploads"] == [])
check("未登录 401", client.get("/settings/background").status_code == 401)

# --- 上传合法图片（自动设为当前） ---
r = client.post("/settings/background/upload", headers=H,
                files={"file": ("bg.png", image_bytes("PNG", (3000, 1500)), "image/png")})
check("上传 201", r.status_code == 201)
img_id = r.json()["id"]
check("上传后为 custom", client.get("/settings/background", headers=H).json()["background"]
      == f"custom:{img_id}")
check("原始文件名保留", r.json()["originalName"] == "bg.png")

# --- 取图：应为 WebP 且长边被压到 <= 2560 ---
r = client.get(f"/settings/background/images/{img_id}", headers=H)
check("取图 200", r.status_code == 200 and r.headers.get("content-type") == "image/webp")
im = Image.open(io.BytesIO(r.content))
check("存储格式 WebP", im.format == "WEBP")
check("长边被限制到 2560", max(im.size) == 2560 and im.size == (2560, 1280))

# --- 非法输入 ---
check("非图片被拒 400",
      client.post("/settings/background/upload", headers=H,
                  files={"file": ("x.txt", b"not an image", "text/plain")}).status_code == 400)
check("GIF 被拒 400",
      client.post("/settings/background/upload", headers=H,
                  files={"file": ("a.gif", image_bytes("GIF", (10, 10)), "image/gif")}
                  ).status_code == 400)
check("超过 10MB 被拒 413",
      client.post("/settings/background/upload", headers=H,
                  files={"file": ("big.png", b"\0" * (10 * 1024 * 1024 + 10), "image/png")}
                  ).status_code == 413)

# --- 选择背景 ---
check("设为默认 BG2",
      client.put("/settings/background", json={"background": "default:BG2"}, headers=H)
      .json()["background"] == "default:BG2")
check("默认键非法 400",
      client.put("/settings/background", json={"background": "default:BG9"}, headers=H)
      .status_code == 400)
check("不存在的自定义图 404",
      client.put("/settings/background", json={"background": "custom:999999"}, headers=H)
      .status_code == 404)
check("格式非法 400",
      client.put("/settings/background", json={"background": "whatever"}, headers=H)
      .status_code == 400)

# --- 背景显示参数 ---
r = client.get("/settings/background", headers=H)
check("默认 auto/cover", r.json()["mode"] == "auto" and r.json()["fit"] == "cover"
      and r.json()["dim"] is None and r.json()["blur"] is None)
r = client.put("/settings/background/display",
               json={"mode": "manual", "dim": 70, "blur": 12, "fit": "contain"}, headers=H)
check("设置显示参数 200",
      r.status_code == 200 and r.json()["mode"] == "manual" and r.json()["dim"] == 70
      and r.json()["blur"] == 12 and r.json()["fit"] == "contain")
r = client.get("/settings/background", headers=H)
check("显示参数已持久化",
      r.json()["mode"] == "manual" and r.json()["dim"] == 70 and r.json()["fit"] == "contain")
check("mode 非法 400",
      client.put("/settings/background/display", json={"mode": "x"}, headers=H).status_code == 400)
check("fit 非法 400",
      client.put("/settings/background/display", json={"fit": "stretch"}, headers=H).status_code == 400)
check("dim 越界 400",
      client.put("/settings/background/display", json={"dim": 101}, headers=H).status_code == 400)
check("blur 越界 400",
      client.put("/settings/background/display", json={"blur": 21}, headers=H).status_code == 400)
check("回到 auto 400 无",
      client.put("/settings/background/display", json={"mode": "auto"}, headers=H).status_code == 200)

# --- 图库上限 10 张（已上传 1 张，再传 9 张后第 10 张失败） ---
for i in range(9):
    rr = client.post("/settings/background/upload", headers=H,
                     files={"file": (f"p{i}.png", image_bytes("PNG", (8, 8)), "image/png")})
    if rr.status_code != 201:
        break
r = client.get("/settings/background", headers=H)
check("图库达到 10 张", len(r.json()["uploads"]) == 10)
check("超过 10 张被拒 400",
      client.post("/settings/background/upload", headers=H,
                  files={"file": ("extra.png", image_bytes("PNG", (8, 8)), "image/png")}
                  ).status_code == 400)

# --- 删除：若为当前背景则回落默认 ---
client.put("/settings/background", json={"background": f"custom:{img_id}"}, headers=H)
r = client.delete(f"/settings/background/images/{img_id}", headers=H)
check("删除后回落默认", r.status_code == 200 and r.json()["background"] == "default:BG1")
check("删除后图库剩 9 张", len(r.json()["uploads"]) == 9)
check("已删除的图 404", client.get(f"/settings/background/images/{img_id}", headers=H).status_code == 404)
check("删除不存在的图 404",
      client.delete("/settings/background/images/999999", headers=H).status_code == 404)

try:
    os.remove(_db_path)
except OSError:
    pass

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
