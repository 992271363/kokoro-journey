"""云存档接口（/api/saves/*）。

- 全部需要 JWT；
- 云存档操作需要 X-Device-Id 头（单设备：与 CloudSession.active_device_id 一致，
  否则 409「云同步已由其他设备接管」）；
- 逐文件上传，服务端按文件落盘，版本为整目录快照，保留最近 10 版。
"""
from __future__ import annotations

import io
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import auth, database, models, schemas
from .. import save_storage
from ..logger import logger

router = APIRouter(prefix="/saves", tags=["Cloud Saves"])

# 用户自定义标识符：字母/数字/-/_/. 与中文，1..64 字符（禁空格与路径分隔符）。
_IDENTIFIER_RE = re.compile(r"^[0-9A-Za-z\u4e00-\u9fff._-]{1,64}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_name(name: Optional[str]) -> str:
    value = (name or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if len(value) > 255:
        raise HTTPException(status_code=400, detail="名称过长")
    return value


def _clean_identifier(identifier: Optional[str]) -> str:
    value = (identifier or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="标识符不能为空")
    if not _IDENTIFIER_RE.match(value):
        raise HTTPException(status_code=400, detail="标识符只能包含字母、数字、-、_、. 与中文（1-64 字符）")
    return value


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
    """「最近写入的存档位」：按写入时间取最新一条已提交版本。"""
    return db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, status="committed"
    ).order_by(models.ServerSaveVersion.created_at.desc(),
               models.ServerSaveVersion.id.desc()).first()


def _game_view(game: models.ServerSaveGame, latest: Optional[models.ServerSaveVersion]) -> dict:
    return {
        "id": game.id,
        "name": game.name,
        "identifier": game.identifier,
        "created_at": game.created_at,
        "updated_at": game.updated_at,
        "latest_version": latest.version_number if latest else None,
        "latest_version_id": latest.id if latest else None,
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
    name = _clean_name(payload.name)
    identifier = _clean_identifier(payload.identifier)
    if db.query(models.ServerSaveGame).filter_by(
            user_id=current_user.id, identifier=identifier).first():
        raise HTTPException(status_code=409, detail="标识符已存在")
    game = models.ServerSaveGame(user_id=current_user.id, name=name, identifier=identifier,
                                 created_at=_now(), updated_at=_now())
    db.add(game)
    db.commit()
    db.refresh(game)
    return _game_view(game, None)


@router.patch("/games/{game_id}", response_model=schemas.SaveGameView)
def update_game(
    game_id: int,
    payload: schemas.SaveGameUpdate,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """改名 / 改标识符；显示名称允许重名，标识符每用户唯一。"""
    game = _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)

    if payload.name is not None:
        game.name = _clean_name(payload.name)
    if payload.identifier is not None:
        identifier = _clean_identifier(payload.identifier)
        clash = db.query(models.ServerSaveGame).filter(
            models.ServerSaveGame.user_id == current_user.id,
            models.ServerSaveGame.identifier == identifier,
            models.ServerSaveGame.id != game_id,
        ).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail="标识符已存在")
        game.identifier = identifier

    game.updated_at = _now()
    db.commit()
    db.refresh(game)
    return _game_view(game, _latest_committed(db, game_id))


@router.get("/games", response_model=List[schemas.SaveGameView])
def list_games(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """只读：网页端等只读客户端无需 X-Device-Id，不参与单设备接管。"""
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


# ---------------- 存档位（固定 10 个） ----------------

@router.get("/games/{game_id}/slots", response_model=List[schemas.SaveSlotView])
def list_slots(
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """返回固定存档位列表（1..SLOT_COUNT）；空槽各字段为 null。只读，不校验设备。"""
    _get_own_game(db, current_user, game_id)
    rows = db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, status="committed"
    ).all()
    by_slot = {v.slot: v for v in rows if v.slot is not None}
    metas = {m.slot: m.label for m in db.query(models.ServerSaveSlotMeta).filter_by(
        game_id=game_id).all()}
    out = []
    for slot in range(1, save_storage.SLOT_COUNT + 1):
        v = by_slot.get(slot)
        out.append({
            "slot": slot,
            "version_id": v.id if v else None,
            "created_at": v.created_at if v else None,
            "total_size": v.total_size if v else None,
            "file_count": v.file_count if v else None,
            "label": metas.get(slot),
        })
    return out


@router.put("/games/{game_id}/slots/{slot}/label")
def set_slot_label(
    game_id: int,
    slot: int,
    payload: schemas.SaveSlotLabelUpdate,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """设置/清除某个存档位的备注名（与槽内容无关，删除内容后仍保留）。"""
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    if not (1 <= slot <= save_storage.SLOT_COUNT):
        raise HTTPException(status_code=400, detail=f"存档位非法（应为 1..{save_storage.SLOT_COUNT}）")

    label = (payload.label or "").strip()
    if len(label) > 32:
        raise HTTPException(status_code=400, detail="备注过长（最多 32 字符）")

    meta = db.query(models.ServerSaveSlotMeta).filter_by(
        game_id=game_id, slot=slot).first()
    if not label:
        if meta is not None:
            db.delete(meta)
            db.commit()
        return {"ok": True, "slot": slot, "label": None}

    if meta is None:
        meta = models.ServerSaveSlotMeta(game_id=game_id, slot=slot,
                                         label=label, updated_at=_now())
        db.add(meta)
    else:
        meta.label = label
        meta.updated_at = _now()
    db.commit()
    return {"ok": True, "slot": slot, "label": label}


@router.delete("/games/{game_id}/slots/{slot}", status_code=status.HTTP_200_OK)
def delete_slot(
    game_id: int,
    slot: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """删除某个存档位内的存档（保留游戏与其它槽位，本地文件不受影响）。"""
    game = _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    if not (1 <= slot <= save_storage.SLOT_COUNT):
        raise HTTPException(status_code=400, detail=f"存档位非法（应为 1..{save_storage.SLOT_COUNT}）")

    versions = db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, slot=slot
    ).all()
    if not versions:
        raise HTTPException(status_code=404, detail="该存档位为空")

    removed: list[int] = []
    for ver in versions:
        db.query(models.ServerSaveFile).filter_by(version_id=ver.id).delete(
            synchronize_session=False)
        removed.append((ver.version_number, ver.id))
        db.delete(ver)
    game.updated_at = _now()
    db.commit()

    for version_number, version_id in removed:
        save_storage.remove_tree(
            save_storage.version_dir(current_user.id, game_id, version_number))
        save_storage.remove_tree(
            save_storage.temp_dir(current_user.id, game_id, version_id))

    logger.info(f"用户 {current_user.username} 删除游戏 {game.name} 存档位 {slot}")
    return {"ok": True, "slot": slot, "removed": [v[0] for v in removed]}

# ---------------- 版本（存档位覆盖写入） ----------------

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

    slot = payload.slot
    if slot is None or not (1 <= slot <= save_storage.SLOT_COUNT):
        raise HTTPException(status_code=400, detail=f"存档位非法（应为 1..{save_storage.SLOT_COUNT}）")

    manifest = [m.model_dump() for m in payload.manifest]
    try:
        save_storage.validate_manifest(manifest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 该槽位当前已提交版本（覆盖目标 / 增量复用基准）
    base = db.query(models.ServerSaveVersion).filter_by(
        game_id=game_id, slot=slot, status="committed"
    ).first()

    max_no = db.query(func.max(models.ServerSaveVersion.version_number)).filter_by(
        game_id=game_id
    ).scalar() or 0
    version_number = max_no + 1

    ver = models.ServerSaveVersion(
        game_id=game_id,
        version_number=version_number,
        slot=slot,
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

    # 增量复用：以「该槽位当前内容」为基准，path+sha256 相同则硬链接进临时目录。
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
        f"用户 {current_user.username} 游戏 {game.name} 开启存档位 {slot} "
        f"(版本 id={ver.id})，需上传 {len(upload_paths)}/{len(manifest)}"
    )
    return {
        "versionId": ver.id,
        "versionNumber": version_number,
        "slot": slot,
        "occupied": base is not None,
        "existing": ({"versionId": base.id, "createdAt": base.created_at,
                      "totalSize": base.total_size, "fileCount": base.file_count}
                     if base is not None else None),
        "uploadPaths": upload_paths,
    }


async def _store_file(user_id: int, game_id: int, version_id: int,
                      rel: str, entry: models.ServerSaveFile,
                      upload: UploadFile) -> int:
    """把上传流写入临时目录并校验大小/sha256；失败清理临时目录并抛 400/413。"""
    tdir = save_storage.temp_dir(user_id, game_id, version_id)
    dest = save_storage.safe_join(tdir, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
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
        raise HTTPException(status_code=400, detail=f"文件大小与清单不一致: {rel}")
    if save_storage.sha256_file(dest).lower() != entry.sha256.lower():
        save_storage.remove_tree(tdir)
        raise HTTPException(status_code=400, detail=f"文件 sha256 与清单不一致: {rel}")
    return size


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

    size = await _store_file(current_user.id, game_id, version_id, rel, entry, file)
    return {"ok": True, "path": rel, "size": size}


@router.post("/games/{game_id}/versions/{version_id}/files-batch", status_code=status.HTTP_201_CREATED)
async def upload_version_files_batch(
    game_id: int,
    version_id: int,
    items: str = Form(...),
    files: List[UploadFile] = File(...),
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """一次请求上传多个文件：items 为 JSON 数组 [{path, sha256}]，与 files 顺序一一对应。"""
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)

    ver = db.query(models.ServerSaveVersion).filter_by(
        id=version_id, game_id=game_id, status="pending"
    ).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="待上传版本不存在")

    try:
        parsed = json.loads(items)
    except Exception:
        raise HTTPException(status_code=400, detail="items 不是合法 JSON")
    if not isinstance(parsed, list) or len(parsed) != len(files):
        raise HTTPException(status_code=400, detail="items 与文件数量不一致")

    uploaded: list[str] = []
    for item, upload in zip(parsed, files):
        try:
            rel = save_storage.safe_relpath((item or {}).get("path"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        entry = db.query(models.ServerSaveFile).filter_by(
            version_id=version_id, relative_path=rel
        ).first()
        if entry is None:
            raise HTTPException(status_code=400, detail=f"文件不在清单中: {rel}")
        await _store_file(current_user.id, game_id, version_id, rel, entry, upload)
        uploaded.append(rel)
    return {"ok": True, "uploaded": uploaded}


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
    save_storage.commit_replace(tdir, vdir)

    # 覆盖语义：删除该槽位原有的已提交版本（其它槽位不受影响）。
    old_versions = db.query(models.ServerSaveVersion).filter(
        models.ServerSaveVersion.game_id == game_id,
        models.ServerSaveVersion.slot == ver.slot,
        models.ServerSaveVersion.id != ver.id,
    ).all()
    for old in old_versions:
        db.query(models.ServerSaveFile).filter_by(version_id=old.id).delete(
            synchronize_session=False)
        save_storage.remove_tree(
            save_storage.version_dir(current_user.id, game_id, old.version_number))
        db.delete(old)

    ver.status = "committed"
    ver.created_at = _now()
    game.updated_at = _now()
    db.commit()

    logger.info(
        f"用户 {current_user.username} 游戏 {game.name} 写入存档位 {ver.slot} "
        f"(版本 id={ver.id})，替换旧版本 {[o.id for o in old_versions]}"
    )
    return {"ok": True, "versionNumber": ver.version_number, "slot": ver.slot,
            "replaced": [o.id for o in old_versions]}


@router.get("/games/{game_id}/versions", deprecated=True)
def list_versions(
    game_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """【已废弃】请改用 `GET /games/{id}/slots`；保留以兼容旧客户端。只读，不校验设备。"""
    _get_own_game(db, current_user, game_id)
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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """只读：文件清单。只读客户端无需 X-Device-Id。"""
    _get_own_game(db, current_user, game_id)
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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """只读：下载单文件。只读客户端无需 X-Device-Id。"""
    _get_own_game(db, current_user, game_id)
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


@router.post("/games/{game_id}/versions/{version_id}/files-batch-download")
def download_version_files_batch(
    game_id: int,
    version_id: int,
    payload: schemas.SaveBatchDownloadRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """一次请求下载多个文件：内存 zip（仅传输、不落盘，不改文件级存储）。

    paths 为空时返回整版；客户端按体积分批调用，单次内容很小。只读，不校验设备。
    """
    _get_own_game(db, current_user, game_id)
    ver = _get_committed_version(db, game_id, version_id)

    rows = db.query(models.ServerSaveFile).filter_by(version_id=ver.id).all()
    entry_by_rel = {r.relative_path: r for r in rows}

    if payload.paths:
        wanted: list[str] = []
        for p in payload.paths:
            try:
                rel = save_storage.safe_relpath(p)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            if rel not in entry_by_rel:
                raise HTTPException(status_code=400, detail=f"文件不在清单中: {rel}")
            wanted.append(rel)
    else:
        wanted = sorted(entry_by_rel.keys())

    vdir = save_storage.version_dir(current_user.id, game_id, ver.version_number)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for rel in wanted:
            full = save_storage.safe_join(vdir, *rel.split("/"))
            if not os.path.isfile(full):
                raise HTTPException(status_code=404, detail=f"文件不存在: {rel}")
            zf.write(full, arcname=rel)
    return Response(content=buf.getvalue(), media_type="application/zip")


@router.delete("/games/{game_id}/versions/{version_id}", deprecated=True)
def delete_version(
    game_id: int,
    version_id: int,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """【已废弃】存档位模型下由覆盖写入取代；保留以兼容旧客户端。"""
    _get_own_game(db, current_user, game_id)
    _require_device(db, current_user, x_device_id)
    ver = db.query(models.ServerSaveVersion).filter_by(id=version_id, game_id=game_id).first()
    if ver is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    vnumber = ver.version_number
    db.query(models.ServerSaveFile).filter_by(version_id=ver.id).delete(
        synchronize_session=False)
    db.delete(ver)
    db.commit()
    save_storage.remove_tree(save_storage.version_dir(current_user.id, game_id, vnumber))
    save_storage.remove_tree(save_storage.temp_dir(current_user.id, game_id, ver.id))
    return {"ok": True}
