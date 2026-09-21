"""用户偏好：背景图库（5 张内置默认 + 账号上传的自定义图）。

- 内置默认图在前端 `public/backgrounds/BG1..BG5.jpg`，服务端只保存选择键；
- 上传图片由 Pillow 统一处理：纠正方向 -> 长边 <= 2560 -> WebP(q=82) -> 剥离元数据；
- 存储：<UPLOADS_DIR>/<user_id>/<uuid>.webp，随账号绑定。
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from .. import auth, database, models, schemas
from ..logger import logger

router = APIRouter(prefix="/settings", tags=["User Settings"])

UPLOADS_ROOT = os.environ.get("UPLOADS_DIR", "/app/uploads")
BACKGROUND_SUBDIR = "backgrounds"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 原始上传上限 10MB
MAX_BACKGROUNDS = 10                  # 每人图库上限
MAX_EDGE = 2560                       # 长边上限（只缩不放）
WEBP_QUALITY = 82
MAX_PIXELS = 50 * 1024 * 1024         # 50MP 防解压炸弹
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_DEFAULT_KEYS = {"BG1", "BG2", "BG3", "BG4", "BG5"}
FALLBACK_BACKGROUND = "default:BG1"

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_dir(user_id: int) -> str:
    path = os.path.join(os.path.abspath(UPLOADS_ROOT), BACKGROUND_SUBDIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _image_url(image_id: int) -> str:
    return f"/settings/background/images/{image_id}"


def _view(b: models.UserBackground) -> dict:
    return {
        "id": b.id,
        "url": _image_url(b.id),
        "original_name": b.original_name,
        "size": b.size,
        "created_at": b.created_at,
    }


def _get_pref(db: Session, user_id: int) -> Optional[models.UserPreference]:
    return db.query(models.UserPreference).filter_by(user_id=user_id).first()


def _state(db: Session, user: models.User) -> dict:
    pref = _get_pref(db, user.id)
    uploads = db.query(models.UserBackground).filter_by(
        user_id=user.id
    ).order_by(models.UserBackground.id.desc()).all()
    return {
        "background": pref.background if pref else FALLBACK_BACKGROUND,
        "mode": pref.bg_mode if pref else "auto",
        "dim": pref.bg_dim if pref else None,
        "blur": pref.bg_blur if pref else None,
        "fit": pref.bg_fit if pref else "cover",
        "uploads": [_view(b) for b in uploads],
    }


def _set_preference(db: Session, user_id: int, value: str) -> models.UserPreference:
    pref = _get_pref(db, user_id)
    if pref is None:
        pref = models.UserPreference(user_id=user_id, background=value, updated_at=_now())
        db.add(pref)
    else:
        pref.background = value
        pref.updated_at = _now()
    return pref


async def _read_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="图片超过 10MB 上限")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="空文件")
    return b"".join(chunks)


def _process_image(raw: bytes) -> bytes:
    """纠正方向、限长边、转 WebP、剥离元数据；非法图片抛 400。"""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="无法识别的图片文件")

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail="仅支持 JPEG / PNG / WebP 图片")
    if img.width * img.height > MAX_PIXELS:
        raise HTTPException(status_code=400, detail="图片分辨率过大")

    had_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = ImageOps.exif_transpose(img)
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    img = img.convert("RGBA" if had_alpha else "RGB")

    out = io.BytesIO()
    img.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return out.getvalue()


@router.get("/background", response_model=schemas.BackgroundState)
def get_background(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return _state(db, current_user)


@router.post("/background/upload", response_model=schemas.UserBackgroundView,
             status_code=status.HTTP_201_CREATED)
async def upload_background(
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """上传背景图；处理成功后自动设为当前背景。"""
    count = db.query(models.UserBackground).filter_by(user_id=current_user.id).count()
    if count >= MAX_BACKGROUNDS:
        raise HTTPException(status_code=400,
                            detail=f"最多上传 {MAX_BACKGROUNDS} 张背景图，请先删除")

    raw = await _read_upload(file)
    processed = _process_image(raw)

    # 先落盘再写库：任何一步失败都要把已落盘的文件清掉，避免孤儿文件。
    filename = f"{uuid.uuid4().hex}.webp"
    dest = os.path.join(_user_dir(current_user.id), filename)
    row = None
    try:
        with open(dest, "wb") as fh:
            fh.write(processed)

        row = models.UserBackground(
            user_id=current_user.id,
            filename=filename,
            original_name=(file.filename or "")[:255] or None,
            content_type="image/webp",
            size=len(processed),
            created_at=_now(),
        )
        db.add(row)
        db.flush()
        _set_preference(db, current_user.id, f"custom:{row.id}")
        db.commit()
    except Exception:
        db.rollback()
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    db.refresh(row)
    logger.info(f"用户 {current_user.username} 上传背景图 id={row.id} ({row.size} bytes)")
    return _view(row)


@router.put("/background", response_model=schemas.BackgroundState)
def set_background(
    payload: schemas.BackgroundUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    value = (payload.background or "").strip()
    if value.startswith("default:"):
        key = value.split(":", 1)[1]
        if key not in ALLOWED_DEFAULT_KEYS:
            raise HTTPException(status_code=400, detail="默认背景不存在")
    elif value.startswith("custom:"):
        try:
            image_id = int(value.split(":", 1)[1])
        except ValueError:
            raise HTTPException(status_code=400, detail="背景参数非法")
        row = db.query(models.UserBackground).filter_by(
            id=image_id, user_id=current_user.id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="背景图不存在")
    else:
        raise HTTPException(status_code=400, detail="背景参数非法")

    _set_preference(db, current_user.id, value)
    db.commit()
    return _state(db, current_user)


@router.put("/background/display", response_model=schemas.BackgroundState)
def set_background_display(
    payload: schemas.BackgroundDisplayUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """设置背景显示参数（auto/manual + 遮罩强度 + 模糊 + 适配方式）。"""
    mode = (payload.mode or "auto").strip().lower()
    if mode not in ("auto", "manual"):
        raise HTTPException(status_code=400, detail="mode 只能为 auto 或 manual")
    fit = (payload.fit or "cover").strip().lower()
    if fit not in ("cover", "contain"):
        raise HTTPException(status_code=400, detail="fit 只能为 cover 或 contain")

    dim = payload.dim
    if dim is not None and not (0 <= dim <= 100):
        raise HTTPException(status_code=400, detail="dim 需在 0..100")
    blur = payload.blur
    if blur is not None and not (0 <= blur <= 20):
        raise HTTPException(status_code=400, detail="blur 需在 0..20")

    pref = _get_pref(db, current_user.id)
    if pref is None:
        pref = _set_preference(db, current_user.id, FALLBACK_BACKGROUND)
    pref.bg_mode = mode
    pref.bg_dim = dim
    pref.bg_blur = blur
    pref.bg_fit = fit
    pref.updated_at = _now()
    db.commit()
    return _state(db, current_user)


@router.delete("/background/images/{image_id}", response_model=schemas.BackgroundState)
def delete_background(
    image_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    row = db.query(models.UserBackground).filter_by(
        id=image_id, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="背景图不存在")

    pref = _get_pref(db, current_user.id)
    if pref is not None and pref.background == f"custom:{row.id}":
        pref.background = FALLBACK_BACKGROUND
        pref.updated_at = _now()

    path = os.path.join(_user_dir(current_user.id), row.filename)
    db.delete(row)
    db.commit()
    try:
        os.remove(path)
    except OSError:
        pass
    logger.info(f"用户 {current_user.username} 删除背景图 id={image_id}")
    return _state(db, current_user)


@router.get("/background/images/{image_id}")
def get_background_image(
    image_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    row = db.query(models.UserBackground).filter_by(
        id=image_id, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="背景图不存在")
    path = os.path.join(_user_dir(current_user.id), row.filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="背景图文件不存在")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=300"})
