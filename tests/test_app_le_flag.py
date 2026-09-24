"""应用「用 Locale Emulator 启动」标记：读写 + 导出/导入往返。"""
import _common  # noqa: F401

import json
import os
import sys

from db import io
from db.repository import AppRepository
from util.path import normalize_exe_path

_common.ensure_db()

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


exe = normalize_exe_path(r"C:\le\demo.exe")
AppRepository.add_app(exe, "demo.exe")
app = AppRepository.get_app_by_path(exe)
check("默认不启用", app is not None and not app.launch_with_le)

check("设置启用返回成功", AppRepository.set_launch_with_le(exe, True))
info = next((a for a in AppRepository.get_all_apps() if a.exe_path == exe), None)
check("列表透出启用状态", info is not None and info.launch_with_le is True)

path = _common.tmpdir("kokoro_app_le_") + os.sep + "export.json"
ok_export, _msg = io.export_data(path, "json")
check("导出成功", ok_export)
with open(path, encoding="utf-8") as f:
    data = json.load(f)
entry = next((a for a in data.get("applications", [])
              if a.get("executable_path") == exe), None)
check("导出包含 launch_with_le=True", entry is not None and entry.get("launch_with_le") is True)

check("置回关闭", AppRepository.set_launch_with_le(exe, False))
check("确认已关闭", not AppRepository.get_app_by_path(exe).launch_with_le)

ok_import, _msg = io.import_data(path)
check("导入成功", ok_import)
check("导入恢复启用状态", AppRepository.get_app_by_path(exe).launch_with_le is True)

# 旧文件缺字段时应按 False 处理，不报错
legacy = _common.tmpdir("kokoro_app_le_legacy_") + os.sep + "legacy.json"
with open(legacy, "w", encoding="utf-8") as f:
    json.dump({"applications": [{
        "uid": "legacy-1",
        "name": "legacy.exe",
        "executable_path": r"C:\le\legacy.exe",
        "launch_path": r"C:\le\legacy.exe",
        "is_watched": True,
        "is_process_path_different": False,
        "is_path_exist": True,
    }]}, f, ensure_ascii=False)
ok_legacy, _msg = io.import_data(legacy)
check("旧文件导入成功", ok_legacy)
legacy_app = AppRepository.get_app_by_path(normalize_exe_path(r"C:\le\legacy.exe"))
check("旧文件缺字段默认关闭", legacy_app is not None and not legacy_app.launch_with_le)

AppRepository.delete_app_completely(exe)
AppRepository.delete_app_completely(normalize_exe_path(r"C:\le\legacy.exe"))

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
