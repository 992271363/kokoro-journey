"""云存档接口（/api/saves/*）。

- 全部需要 JWT；
- 云存档操作需要 X-Device-Id 头（单设备：与 CloudSession.active_device_id 一致，
  否则 409「云同步已由其他设备接管」）；
- 逐文件上传，服务端按文件落盘，版本为整目录快照，保留最近 10 版。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import auth, database, models, schemas
from .. import save_storage
from ..logger import logger

router = APIRouter(prefix="/saves", tags=["Cloud Saves"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_device(db: Session, user: models.User, device_id: Optional[str]) -> models.ServerCloudSession:
    if not device_id:
        raise HTTPException(status_code=400, detail="缺少 X-Device-Id 请求头")
    sess = db.query(models.ServerCloudSession).filter_by(user_id=user.id).first()
    if sess is None:
        # 首次使用即登记当前设备
        sess = models.ServerCloudSession(user_id=user.id, active_device_id=device_id, updated_at=_now())
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return sess
    if sess.active_device_id != device_id:
        logger.warning(
            f"用户 {user.username} 云同步设备冲突：当前 {sess.active_device_id}，请求 {device_id}"
        )
        raise HTTPException(
            status_code=409,
            detail="云同步已由其他设备接管",
            headers={"X-Cloud-Error": "taken_over"},
        )
    return sess


def _get_own_game(db: Session, user: models.User, game_id: int) -> models.ServerSaveGame:
    game = db.query(models.ServerSaveGame).filter_by(id=game_id, user_id=user.id).first()
    if game is None:
        raise HTTPException(status_code=404, detail="游戏不存在")
    return game


def _get_committed_version(db: Session, game_id: int, version_id: int) -> models.ServerSaveVersion:
    ver = db.query(models.ServerSaveVersion).filter_by(
        id=version_id, game_id=game_id, status="committed"
    ).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    return ver


def _latest_committed(db: Session, game_id: int) -> Optional[models.ServerSaveVersion]:
    return db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, status="committed"
    ).order_by(models.ServerSaveVersion.version_number.desc()).first()


def _game_view(game: models.ServerSaveGame, latest: Optional[models.ServerSaveVersion]) -> dict:
    return {
        "id": game.id,
        "name": game.name,
        "created_at": game.created_at,
        "updated_at": game.updated_at,
        "latest_version": latest.version_number if latest else None,
        "latest_total_size": latest.total_size if latest else None,
        "latest_file_count": latest.file_count if latest else None,
        "latest_created_at": latest.created_at if latest else None,
    }


# ---------------- 设备登记（单设备接管） ----------------

@router.post("/device/claim", response_model=schemas.SaveDeviceInfo)
def claim_device(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not x_device_id:
        raise HTTPException(status_code=400, detail="缺少 X-Device-Id 请求头")
    sess = db.query(models.ServerCloudSession).filter_by(user_id=current_user.id).first()
    previous = sess.active_device_id if sess else None
    if sess is None:
        db.add(models.ServerCloudSession(user_id=current_user.id,
                                         active_device_id=x_device_id, updated_at=_now()))
    else:
        sess.active_device_id = x_device_id
        sess.updated_at = _now()
    db.commit()
    logger.info(f"用户 {current_user.username} 云同步设备登记: {x_device_id}（原: {previous}）")
    return {"active_device_id": x_device_id, "previous_device_id": previous}


@router.get("/device", response_model=schemas.SaveDeviceInfo)
def get_device(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    sess = db.query(models.ServerCloudSession).filter_by(user_id=current_user.id).first()
    return {"active_device_id": sess.active_device_id if sess else None, "previous_device_id": None}


# ---------------- 游戏 ----------------

@router.post("/games", response_model=schemas.SaveGameView, status_code=status.HTTP_201_CREATED)
def create_game(
    payload: schemas.SaveGameCreate,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_device(db, current_user, x_device_id)
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if db.query(models.ServerSaveGame).filter_by(user_id=current_user.id, name=name).first():
        raise HTTPException(status_code=409, detail="同名游戏已存在")
    game = models.ServerSaveGame(user_id=current_user.id, name=name,
                                 created_at=_now(), updated_at=_now())
    db.add(game)
    db.commit()
    db.refresh(game)
    return _game_view(game, None)


@router.get("/games", response_model=List[schemas.SaveGameView])
def list_games(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_device(db, current_user, x_device_id)
    games = db.query(models.ServerSaveGame).filter_by(
        user_id=current_user.id
    ).order_by(models.ServerSaveGame.id).all()
    return [_game_view(g, _latest_committed(db, g.id)) for g in games]


@router.delete("/games/{game_id}", status_code=status.HTTP_200_OK)
def delete_game(
    game_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_device(db, current_user, x_device_id)
    game = _get_own_game(db, current_user, game_id)
    db.delete(game)
    db.commit()
    save_storage.remove_tree(save_storage.game_dir(current_user.id, game_id))
    return {"ok": True}


# ---------------- 版本 ----------------

@router.post("/games/{game_id}/versions", status_code=status.HTTP_201_CREATED)
def begin_version(
    game_id: int,
    payload: schemas.SaveVersionCreate,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    game = _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)

    manifest = [m.model_dump() for m in payload.manifest]
    try:
        save_storage.validate_manifest(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    max_no = db.query(func.max(models.ServerSaveVersion.version_number)).filter_by(
        game_id=game_id
    ).scalar() or 0
    version_number = max_no + 1

    ver = models.ServerSaveVersion(
        game_id=game_id,
        version_number=version_number,
        status="pending",
        total_size=sum(int(m["size"]) for m in manifest),
        file_count=len(manifest),
        created_at=_now(),
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)

    gpath = save_storage.game_dir(current_user.id, game_id)
    tdir = save_storage.temp_dir(current_user.id, game_id, ver.id)
    save_storage.remove_tree(tdir)
    save_storage.ensure_dir(tdir)

    # 增量复用：与上一已提交版本 path+sha256 相同的文件，直接硬链接进临时目录，
    # 免去重新上传；客户端只上传 upload_paths 里的文件。
    base = _latest_committed(db, game_id)
    base_files: dict[str, str] = {}
    base_dir = None
    if base is not None:
        base_dir = save_storage.version_dir(current_user.id, game_id, base.version_number)
        for row in db.query(models.ServerSaveFile).filter_by(version_id=base.id).all():
            base_files[row.relative_path] = (row.sha256 or "").lower()

    upload_paths: list[str] = []
    for m in manifest:
        rel = save_storage.safe_relpath(m["path"])
        digest = str(m["sha256"]).lower()
        reused = False
        if base_dir is not None and base_files.get(rel) == digest:
            src = save_storage.safe_join(base_dir, *rel.split("/"))
            dst = save_storage.safe_join(tdir, *rel.split("/"))
            if os.path.isfile(src):
                try:
                    save_storage.link_or_copy(src, dst)
                    reused = True
                except OSError:
                    reused = False
        if not reused:
            upload_paths.append(rel)

        db.add(models.ServerSaveFile(
            version_id=ver.id,
            relative_path=rel,
            size=int(m["size"]),
            sha256=digest,
            mtime_ns=m.get("mtime_ns"),
        ))
    db.commit()
    logger.info(
        f"用户 {current_user.username} 游戏 {game.name} 开启版本 v{version_number} "
        f"(id={ver.id})，需上传 {len(upload_paths)}/{len(manifest)}"
    )
    return {"versionId": ver.id, "versionNumber": version_number, "uploadPaths": upload_paths}


@router.post("/games/{game_id}/versions/{version_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_version_file(
    game_id: int,
    version_id: int,
    path: str = Form(...),
    sha256: str = Form(...),
    file: UploadFile = File(...),
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)

    ver = db.query(models.ServerSaveVersion).filter_by(
        id=version_id, game_id=game_id, status="pending"
    ).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="待上传版本不存在")

    try:
        rel = save_storage.safe_relpath(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    entry = db.query(models.ServerSaveFile).filter_by(
        version_id=version_id, relative_path=rel
    ).first()
    if entry is None:
        raise HTTPException(status_code=400, detail="文件不在清单中")

    tdir = save_storage.temp_dir(current_user.id, game_id, version_id)
    dest = save_storage.safe_join(tdir, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > save_storage.MAX_FILE_BYTES:
                out.close()
                save_storage.remove_tree(tdir)
                raise HTTPException(status_code=413, detail="单文件超过服务端上限")
            out.write(chunk)

    if size != entry.size:
        save_storage.remove_tree(tdir)
        raise HTTPException(status_code=400, detail="文件大小与清单不一致")
    if save_storage.sha256_file(dest).lower() != entry.sha256.lower():
        save_storage.remove_tree(tdir)
        raise HTTPException(status_code=400, detail="文件 sha256 与清单不一致")
    return {"ok": True, "path": rel, "size": size}


@router.post("/games/{game_id}/versions/{version_id}/commit")
def commit_version(
    game_id: int,
    version_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    game = _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)

    ver = db.query(models.ServerSaveVersion).filter_by(
        id=version_id, game_id=game_id, status="pending"
    ).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="待提交版本不存在")

    tdir = save_storage.temp_dir(current_user.id, game_id, version_id)
    files = db.query(models.ServerSaveFile).filter_by(version_id=version_id).all()
    for f in files:
        p = save_storage.safe_join(tdir, *f.relative_path.split("/"))
        if not os.path.isfile(p):
            raise HTTPException(status_code=400, detail=f"缺少文件: {f.relative_path}")
        if os.path.getsize(p) != f.size:
            raise HTTPException(status_code=400, detail=f"大小不符: {f.relative_path}")
        if save_storage.sha256_file(p).lower() != f.sha256.lower():
            raise HTTPException(status_code=400, detail=f"sha256 不符: {f.relative_path}")

    vdir = save_storage.version_dir(current_user.id, game_id, ver.version_number)
    save_storage.atomic_commit(tdir, vdir)

    ver.status = "committed"
    ver.created_at = _now()
    game.updated_at = _now()
    db.commit()

    gpath = save_storage.game_dir(current_user.id, game_id)
    pruned = save_storage.prune_versions(gpath, keep=save_storage.KEEP_VERSIONS)
    if pruned:
        db.query(models.ServerSaveVersion).filter(
            models.ServerSaveVersion.game_id == game_id,
            models.ServerSaveVersion.version_number.in_(pruned),
        ).delete(synchronize_session=False)
        db.commit()

    logger.info(f"用户 {current_user.username} 游戏 {game.name} 提交版本 v{ver.version_number}；剪裁 {pruned}")
    return {"ok": True, "versionNumber": ver.version_number, "pruned": pruned}


@router.get("/games/{game_id}/versions")
def list_versions(
    game_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    versions = db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, status="committed"
    ).order_by(models.ServerSaveVersion.version_number.desc()).all()
    return [
        {
            "id": v.id,
            "versionNumber": v.version_number,
            "totalSize": v.total_size,
            "fileCount": v.file_count,
            "createdAt": v.created_at,
        }
        for v in versions
    ]


@router.get("/games/{game_id}/versions/{version_id}/files")
def list_version_files(
    game_id: int,
    version_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    ver = _get_committed_version(db, game_id, version_id)
    rows = db.query(models.ServerSaveFile).filter_by(version_id=ver.id).order_by(
        models.ServerSaveFile.relative_path
    ).all()
    return [
        {"path": r.relative_path, "size": r.size, "sha256": r.sha256, "mtimeNs": r.mtime_ns}
        for r in rows
    ]


@router.get("/games/{game_id}/versions/{version_id}/files/download")
def download_version_file(
    game_id: int,
    version_id: int,
    path: str,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    ver = _get_committed_version(db, game_id, version_id)
    try:
        rel = save_storage.safe_relpath(path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    vdir = save_storage.version_dir(current_user.id, game_id, ver.version_number)
    full = save_storage.safe_join(vdir, *rel.split("/"))
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(full, media_type="application/octet-stream",
                        filename=os.path.basename(rel))


@router.delete("/games/{game_id}/versions/{version_id}")
def delete_version(
    game_id: int,
    version_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    ver = db.query(models.ServerSaveVersion).filter_by(id=version_id, game_id=game_id).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    vnumber = ver.version_number
    db.delete(ver)
    db.commit()
    save_storage.remove_tree(save_storage.version_dir(current_user.id, game_id, vnumber))
    return {"ok": True}
