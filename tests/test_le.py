"""Locale Emulator 辅助：命令组装 / 配置解析 / 路径定位 / 就绪检查（离线）。"""
import _common  # noqa: F401

import os
import sys

from util import le

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# ---- 编号规范化 ----
check("normalize_guid 去花括号转小写",
      le.normalize_guid("{8C9D8552-F076-4491-9F1C-9D2DE66786A6}")
      == "8c9d8552-f076-4491-9f1c-9d2de66786a6")
check("is_valid_guid 合法", le.is_valid_guid("8c9d8552-f076-4491-9f1c-9d2de66786a6"))
check("is_valid_guid 带花括号也算合法",
      le.is_valid_guid("{8c9d8552-f076-4491-9f1c-9d2de66786a6}"))
check("is_valid_guid 非法", not le.is_valid_guid("not-a-guid"))

# ---- 命令组装 ----
cmd = le.build_le_command(r"C:\LE\LEProc.exe",
                          "{8C9D8552-F076-4491-9F1C-9D2DE66786A6}",
                          r"C:\games\g.exe")
check("命令为 -runas <编号> <目标>",
      cmd[0].endswith("LEProc.exe") and cmd[1] == "-runas"
      and cmd[2] == "8c9d8552-f076-4491-9f1c-9d2de66786a6"
      and cmd[3].endswith("g.exe"))

# ---- 解析区域配置 ----
XML = """<?xml version="1.0" encoding="utf-8"?>
<LEConfig>
  <Profiles>
    <Profile Name="Run in Japanese" Guid="8c9d8552-f076-4491-9f1c-9d2de66786a6" MainMenu="true">
      <Location>ja-JP</Location><RunAsAdmin>true</RunAsAdmin>
    </Profile>
    <Profile Name="china" Guid="9cb659fa-67f8-4ae0-89a2-02601da3d675" MainMenu="false">
      <Location>zh</Location><RunAsAdmin>false</RunAsAdmin>
    </Profile>
    <Profile Name="bad" Guid="nope" MainMenu="false"><Location>x</Location></Profile>
  </Profiles>
</LEConfig>
"""
tmp = _common.tmpdir("kokoro_le_")
cfg = os.path.join(tmp, "LEConfig.xml")
with open(cfg, "w", encoding="utf-8") as f:
    f.write(XML)

profiles = le.parse_profiles(cfg)
check("解析出 2 套有效配置（非法编号跳过）", len(profiles) == 2)
check("字段解析正确",
      profiles[0]["name"] == "Run in Japanese"
      and profiles[0]["location"] == "ja-JP"
      and profiles[0]["run_as_admin"] is True
      and profiles[0]["guid"] == "8c9d8552-f076-4491-9f1c-9d2de66786a6")
check("默认选中「主菜单」那套", le.pick_default_index(profiles) == 0)
check("无主菜单时按日语兜底",
      le.pick_default_index([
          {"name": "x", "guid": "a", "location": "zh", "main_menu": False},
          {"name": "Run in Japanese", "guid": "b", "location": "ja-JP", "main_menu": False},
      ]) == 1)
check("空列表 → -1", le.pick_default_index([]) == -1)
check("显示文字含名称与管理员标记", "Run in Japanese" in le.profile_label(profiles[0])
      and "需管理员" in le.profile_label(profiles[0]))

bad = os.path.join(tmp, "bad.xml")
with open(bad, "w", encoding="utf-8") as f:
    f.write("<LEConfig><Profiles>")
check("畸形 XML → 空列表", le.parse_profiles(bad) == [])
check("文件不存在 → 空列表", le.parse_profiles(os.path.join(tmp, "nope.xml")) == [])
check("None → 空列表", le.parse_profiles(None) == [])

# ---- 路径定位 ----
root = _common.tmpdir("kokoro_le_root_")
os.makedirs(os.path.join(root, "bin"))
with open(os.path.join(root, "bin", "LEProc.exe"), "wb"):
    pass
with open(os.path.join(root, "LEConfig.xml"), "w", encoding="utf-8") as f:
    f.write(XML)

check("在根目录找到配置", le.find_leconfig(root).endswith("LEConfig.xml"))
check("在一层子目录找到启动程序", le.find_leproc(root).endswith("LEProc.exe"))
check("空路径 → None", le.find_leproc("") is None)
check("不存在目录 → None", le.find_leproc(os.path.join(root, "nope")) is None)

# ---- 就绪检查 ----
guid = profiles[0]["guid"]
check("配置齐全 → 就绪", le.check_ready(root, guid)[0] is True)
check("未设置文件夹 → 不就绪", le.check_ready("", guid)[0] is False)
check("目录不存在 → 不就绪", le.check_ready(os.path.join(root, "nope"), guid)[0] is False)
check("缺启动程序 → 不就绪", le.check_ready(tmp, guid)[0] is False)
check("未选区域配置 → 不就绪", le.check_ready(root, "")[0] is False)

# ---- 启动失败路径（不会真的启动） ----
check("启动程序不存在 → 失败",
      le.launch_with_le(os.path.join(root, "nope.exe"), guid, __file__)[0] is False)
check("目标不存在 → 失败",
      le.launch_with_le(le.find_leproc(root), guid,
                        os.path.join(root, "nope.exe"))[0] is False)
check("编号非法 → 失败",
      le.launch_with_le(le.find_leproc(root), "bad", __file__)[0] is False)

# ---- 本机若装了 LE，额外校验真实配置可解析 ----
real_cfg = r"D:\LE\LEConfig.xml"
if os.path.isfile(real_cfg):
    real_profiles = le.parse_profiles(real_cfg)
    check("本机 LE 配置可解析（≥1 套）", len(real_profiles) >= 1)
    if real_profiles:
        picked = real_profiles[le.pick_default_index(real_profiles)]
        check("本机默认落在日语区域", picked["location"].lower().startswith("ja"))
else:
    print("[SKIP] 本机未发现 Locale Emulator 配置，跳过真实配置校验")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
