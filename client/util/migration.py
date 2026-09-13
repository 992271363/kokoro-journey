"""数据存储位置迁移。

设置页更改存储位置时只写入待迁移标记（pendingDataMigration），真正的文件
搬移在下次启动、绑定数据库路径之前执行——此时旧进程已释放 SQLite 句柄，
避免 Windows 下文件被占用导致失败。

安全原则：任何一步失败都**不删除源文件**；只有全部复制并校验成功后才删除源，
保证迁移失败时原数据仍可恢复。
"""
import os
import shutil

from util.config import Settings

# 需要随存储位置一起迁移的文件（旧目录 *_bak 备份不迁移）
MIGRATE_FILES = (
    "local_client.db",
    "failed_sessions.json",
    "failed_sessions_dead.json",
)


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def next_backup_path(db_path: str) -> str:
    """返回第一个不存在的备份路径：<db_path>.Back1 / .Back2 / ..."""
    n = 1
    while True:
        candidate = f"{db_path}.Back{n}"
        if not os.path.exists(candidate):
            return candidate
        n += 1


def _update_state_safe(data_dir: str) -> None:
    try:
        from util.state import update_state

        update_state(data_dir)
    except Exception as e:
        print(f"[Migrate] 更新卸载状态失败: {e}")


def apply_pending_migration() -> None:
    """执行待处理的存储位置迁移；无待迁移标记则直接返回。"""
    pending = Settings().get("pendingDataMigration")
    if not isinstance(pending, dict):
        return

    src = pending.get("from")
    dst = pending.get("to")
    mode = pending.get("mode")

    if not src or not dst or mode == "use_target" or _norm(src) == _norm(dst):
        # 使用目标库 / 同目录：无需搬移文件
        Settings().set("pendingDataMigration", None)
        return

    try:
        os.makedirs(dst, exist_ok=True)
    except OSError as e:
        print(f"[Migrate][Error] 无法创建目标目录 {dst}: {e}（保留待迁移标记）")
        return

    entries = []  # [(src, dst)]

    src_db = os.path.join(src, "local_client.db")
    dst_db = os.path.join(dst, "local_client.db")
    if os.path.exists(src_db):
        if os.path.exists(dst_db):
            backup = next_backup_path(dst_db)
            try:
                shutil.copy2(dst_db, backup)
            except OSError as e:
                print(f"[Migrate][Error] 备份目标数据库失败: {e}（保留源文件与标记）")
                return
            print(f"[Migrate] 目标已有数据库，已备份为 {os.path.basename(backup)}")
        entries.append((src_db, dst_db))

    for name in MIGRATE_FILES:
        if name == "local_client.db":
            continue
        s = os.path.join(src, name)
        if os.path.exists(s):
            entries.append((s, os.path.join(dst, name)))

    if not entries:
        print(f"[Migrate] 无可迁移文件（源目录 {src}）")
        Settings().set("pendingDataMigration", None)
        _update_state_safe(dst)
        return

    try:
        # 阶段 1：全部复制（源文件保持不动）
        for s, d in entries:
            shutil.copy2(s, d)
        # 阶段 2：全部校验
        for s, d in entries:
            if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(s):
                raise OSError(f"校验失败: {d}")
        # 阶段 3：全部确认无误后才删除源文件
        for s, _ in entries:
            os.remove(s)
    except Exception as e:
        print(f"[Migrate][Error] 迁移失败，源文件已保留: {e}（保留待迁移标记）")
        return

    Settings().set("pendingDataMigration", None)
    _update_state_safe(dst)
    print(f"[Migrate] 迁移完成: {src} -> {dst}（{len(entries)} 个文件）")
