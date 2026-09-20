"""存档位：自动选槽策略 / 存档位选择对话框（离屏，不联网）。"""
import _common  # noqa: F401

import sys

from PySide6.QtWidgets import QApplication

import core.save_sync as ss

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# --- 常量 ---
check("存档位总数为 10", ss.SLOT_COUNT == 10)
check("每页显示 5 个", ss.SLOT_PAGE_SIZE == 5)

# --- pick_auto_slot ---
check("全空选最小空槽", ss.pick_auto_slot(
    [{"slot": 1, "versionId": None}, {"slot": 2, "versionId": None}]) == 1)
check("有空格优先空槽", ss.pick_auto_slot([
    {"slot": 1, "versionId": 9, "createdAt": "2026-01-01"},
    {"slot": 2, "versionId": None},
    {"slot": 3, "versionId": 8, "createdAt": "2026-02-01"},
]) == 2)
check("无空槽覆盖最旧日期", ss.pick_auto_slot([
    {"slot": 1, "versionId": 9, "createdAt": "2026-03-01"},
    {"slot": 2, "versionId": 8, "createdAt": "2026-01-01"},
    {"slot": 3, "versionId": 7, "createdAt": "2026-02-01"},
]) == 2)
check("空列表返回 None", ss.pick_auto_slot([]) is None)

# --- SlotPickerDialog ---
from ui.personal_center import SlotPickerDialog, SlotCard  # noqa: E402

slots = [{"slot": i, "versionId": None} for i in range(1, 11)]
slots[0] = {"slot": 1, "versionId": 11, "createdAt": "2026-05-01T10:20:30", "totalSize": 2048}
slots[1] = {"slot": 2, "versionId": 12, "createdAt": "2026-05-02T10:20:30", "totalSize": 4096}

dlg = SlotPickerDialog(None, slots, mode="upload")
check("共 2 页", dlg._page_count == 2)
check("共 10 个单选", len(dlg._group.buttons()) == 10)
check("初始未选中", dlg.selected is None)

by_slot = {c.slot: c for c in dlg.findChildren(SlotCard)}
check("10 张卡片", len(by_slot) == 10)
check("已占用卡片标记", by_slot[1].property("slot_occupied") is True)
check("空槽卡片不标记", by_slot[3].property("slot_occupied") is False)
check("空槽显示「空」", by_slot[3].time_label.text() == "空")
check("占用显示时间", by_slot[1].time_label.text().startswith("2026-05-01"))
check("占用显示大小", by_slot[2].size_label.text() and "4" in by_slot[2].size_label.text())

by_slot[2].radio.setChecked(True)
check("选中槽位 2", dlg.selected == 2 and dlg.selected_slot() == 2)
check("selected_info 返回槽位信息", (dlg.selected_info() or {}).get("versionId") == 12)

dlg._goto(1)
check("翻到第 2 页", dlg._pages.currentIndex() == 1)
check("第 2 页：上一页可用", dlg.btn_prev.isEnabled())
check("第 2 页：下一页禁用", not dlg.btn_next.isEnabled())
dlg.close()

for mode in ("upload", "download", "view", "delete"):
    d = SlotPickerDialog(None, slots, mode=mode)
    check(f"模式 {mode} 有标题", bool(d.windowTitle()))
    d.close()

# --- 删除模式：空槽不可选，且 _on_ok 拒绝空槽 ---
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

dd = SlotPickerDialog(None, slots, mode="delete")
dcards = {c.slot: c for c in dd.findChildren(SlotCard)}
check("删除模式：已占用槽可选", dcards[1].radio.isEnabled())
check("删除模式：空槽不可选", not dcards[3].radio.isEnabled())
dd.selected = 3  # 绕过 UI 直接模拟空槽选择
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
dd._on_ok()
check("删除模式：空槽不通过校验", dd.result() != QDialog.Accepted)
dd.close()

# --- 存档位备注名：显示 + 重命名 ---
from PySide6.QtWidgets import QInputDialog  # noqa: E402

slots_l = [{"slot": i, "versionId": None} for i in range(1, 11)]
slots_l[0] = {"slot": 1, "versionId": 11, "createdAt": "2026-05-01T10:20:30",
              "totalSize": 2048, "label": "第一章"}
dl = SlotPickerDialog(None, slots_l, mode="upload", token="t", server_id=5)
lcards = {c.slot: c for c in dl.findChildren(SlotCard)}
check("卡片显示备注", lcards[1].name_label.text() == "第一章")
check("未命名显示占位", lcards[2].name_label.text() == "未命名")
check("有 token 时可重命名", dl._can_rename())

ss.set_slot_label = lambda t, sid, slot, label: (
    True, {"ok": True, "slot": slot, "label": label or None})
QInputDialog.getText = staticmethod(lambda *a, **k: ("第三章", True))
dl.rename_slot(3)
check("重命名更新卡片", lcards[3].name_label.text() == "第三章")
check("重命名更新缓存", (dl._slots.get(3) or {}).get("label") == "第三章")

QInputDialog.getText = staticmethod(lambda *a, **k: ("", True))
dl.rename_slot(3)
check("清空备注回到未命名", lcards[3].name_label.text() == "未命名"
      and (dl._slots.get(3) or {}).get("label") is None)

QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
_prev = lcards[3].name_label.text()
QInputDialog.getText = staticmethod(lambda *a, **k: ("x" * 33, True))
dl.rename_slot(3)
check("超长备注被拒", lcards[3].name_label.text() == _prev)
dl.close()

dl2 = SlotPickerDialog(None, slots_l, mode="upload")
check("无 token 时不启用重命名", not dl2._can_rename())
dl2.close()

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
